from __future__ import annotations

import hashlib
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_experiment import (
    BattleOutcomeCaptureBinding,
    BattleOutcomeExperimentPlan,
    battle_outcome_distinct_hidden_embedding_count,
    battle_outcome_hidden_menu_sha256,
    battle_outcome_menu_sha256,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_battle_outcome_learning_cycle.py")
)
SCRIPT_GLOBALS = SCRIPT["_run"].__globals__


def _model(*, output_weights: tuple[float, float] = (1.0, 0.0)) -> MaskedMLPMoveRanker:
    input_weights = np.zeros((2, len(FEATURE_NAMES)), dtype=np.float64)
    input_weights[0, 0] = 1.0
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=input_weights,
        hidden_bias=np.zeros(2, dtype=np.float64),
        output_weights=np.asarray(output_weights, dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )


def _sha(model: MaskedMLPMoveRanker) -> str:
    return hashlib.sha256(model.to_json().encode("ascii")).hexdigest()


def _digest(marker: str) -> str:
    return hashlib.sha256(marker.encode("ascii")).hexdigest()


def _features() -> BattleFeatureBatch:
    return BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=(
            tuple(-1.0 if index == 0 else 0.0 for index in range(len(FEATURE_NAMES))),
            tuple(1.0 if index == 0 else 0.0 for index in range(len(FEATURE_NAMES))),
        ),
        legal_mask=(True, True),
        current_pp=(10.0, 10.0),
        slot_indices=(0, 1),
        schema_id=FEATURE_SCHEMA_ID,
    )


def _binding(
    partition: ScenarioPartition,
    marker: str,
    *,
    commit: str,
    base_model: MaskedMLPMoveRanker,
) -> BattleOutcomeCaptureBinding:
    source_state = _digest(f"{marker}:source-state")
    envelope = _digest(f"{marker}:envelope")
    assignment = _digest(f"{marker}:assignment")
    features = _features()
    return BattleOutcomeCaptureBinding(
        partition=partition,
        capture_id=f"{partition.value}-{marker}",
        manifest_sha256=_digest(f"{marker}:manifest"),
        state_sha256=_digest(f"{marker}:state"),
        initial_observation_sha256=_digest(f"{marker}:observation"),
        source_commit=commit,
        source_state_sha256=source_state,
        source_slot_id=f"red-goal-v1-{partition.value}-{marker}",
        source_assignment_id=assignment,
        source_context_id=_digest(f"{marker}:context"),
        source_envelope_sha256=envelope,
        root_lineage_id=f"red-goal-root-{assignment}",
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=source_state,
            envelope_sha256=envelope,
        ),
        menu_sha256=battle_outcome_menu_sha256(features),
        supported_candidate_count=2,
        distinct_candidate_vector_count=2,
        hidden_embedding_sha256=battle_outcome_hidden_menu_sha256(
            base_model,
            features,
        ),
        distinct_hidden_embedding_count=(
            battle_outcome_distinct_hidden_embedding_count(base_model, features)
        ),
        expected_map=11 if partition is ScenarioPartition.TRAIN else 197,
        expected_battle_state=1,
    )


def _plan(base_model: MaskedMLPMoveRanker) -> BattleOutcomeExperimentPlan:
    commit = "a" * 40
    return BattleOutcomeExperimentPlan(
        experiment_id="red-battle-cycle-001",
        source_commit=commit,
        source_bundle_sha256="b" * 64,
        runner_sha256="c" * 64,
        materializer_sha256="d" * 64,
        registry_source_commit="e" * 40,
        registry_source_bundle_sha256="f" * 64,
        registry_sha256="1" * 64,
        context_catalog_sha256="2" * 64,
        rom_sha256="3" * 64,
        runtime_identity_sha256="4" * 64,
        numpy_runtime_sha256="5" * 64,
        base_model_sha256=_sha(base_model),
        controller_timing_sha256="6" * 64,
        captures=(
            _binding(
                ScenarioPartition.TRAIN,
                "train",
                commit=commit,
                base_model=base_model,
            ),
            _binding(
                ScenarioPartition.DEVELOPMENT,
                "development",
                commit=commit,
                base_model=base_model,
            ),
        ),
    )


def _capture(binding: BattleOutcomeCaptureBinding) -> SimpleNamespace:
    return SimpleNamespace(
        manifest=SimpleNamespace(
            capture_id=binding.capture_id,
            partition=binding.partition,
            source_commit=binding.source_commit,
            source_state_sha256=binding.source_state_sha256,
            root_lineage_id=binding.root_lineage_id,
            state_sha256=binding.state_sha256,
            initial_observation_sha256=binding.initial_observation_sha256,
            expected_map=binding.expected_map,
            expected_battle_state=binding.expected_battle_state,
        ),
        manifest_sha256=binding.manifest_sha256,
    )


class Writer:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []
        self.durable: list[bool] = []
        self.summary = SimpleNamespace(
            public_dict=lambda: {
                "artifact_id": "battle-outcome-test",
                "status": "complete",
            }
        )

    def __enter__(self) -> Writer:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def append(
        self,
        stream: str,
        record: dict[str, object],
        *,
        durable: bool = False,
    ) -> None:
        self.records.append((stream, record))
        self.durable.append(durable)


class Store:
    def __init__(self) -> None:
        self.writer = Writer()

    def begin_artifact(self, artifact_id: str, *, kind: str) -> Writer:
        assert artifact_id.startswith("bo-cycle-")
        assert len(artifact_id) <= 80
        assert kind == "battle_outcome_cycle"
        return self.writer


class ClaimTransaction:
    def __init__(self, claims: dict[str, object]) -> None:
        self.claims = claims

    def __enter__(self) -> ClaimTransaction:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def available(self, logical: str, physical: str) -> bool:
        return all(
            logical not in claim.identities and physical not in claim.identities
            for claim in self.claims.values()
        )

    def claim(self, claim):  # type: ignore[no-untyped-def]
        if not self.available(claim.logical_root_sha256, claim.physical_root_sha256):
            raise RuntimeError("already claimed")
        self.claims[claim.claim_sha256] = claim
        return claim


def _exercise(
    monkeypatch,
    *,
    train_informative: bool,
    development_informative: bool,
    updated_wins: int = 1,
    base_wins: int = 0,
) -> tuple[dict[str, object], Writer, list[str]]:  # type: ignore[no-untyped-def]
    base_model = _model()
    updated_model = _model(output_weights=(-1.0, 0.0))
    plan = _plan(base_model)
    train_capture = _capture(plan.train)
    development_capture = _capture(plan.development)
    opened: list[str] = []
    features = _features()
    if updated_wins:
        utilities = (1.0, 0.0)
    elif base_wins:
        utilities = (0.0, 1.0)
    else:
        utilities = (1.0, 1.0)
    outcomes = tuple(
        SimpleNamespace(
            utility=utility,
            public_dict=lambda utility=utility: {"utility": utility},
        )
        for utility in utilities
    )

    def collection(capture, *, informative: bool):  # type: ignore[no-untyped-def]
        binding = plan.train if capture is train_capture else plan.development
        example = SimpleNamespace(
            learner_update_eligible=informative,
            outcomes=outcomes,
            features=features,
            root_lineage_id=binding.root_lineage_id,
            initial_state_sha256=binding.state_sha256,
        )
        return SimpleNamespace(
            example=example,
            outcomes=outcomes,
            initial_observation_sha256=binding.initial_observation_sha256,
            public_dict=lambda: {"capture_id": binding.capture_id},
        )

    train_collection = collection(train_capture, informative=train_informative)
    development_collection = collection(
        development_capture,
        informative=development_informative,
    )
    updated_sha256 = _sha(updated_model)
    update = SimpleNamespace(
        model=updated_model,
        report=SimpleNamespace(
            base_model_sha256=plan.base_model_sha256,
            updated_model_sha256=updated_sha256,
            training_example_count=1,
            training_root_lineage_ids=(plan.train.root_lineage_id,),
            training_state_sha256=(plan.train.state_sha256,),
            epochs=plan.epochs,
            learning_rate=plan.learning_rate,
            prior_l2=plan.prior_l2,
            public_dict=lambda: {"updated_model_sha256": updated_sha256},
        ),
    )
    claims: dict[str, object] = {}
    store = Store()
    source = SimpleNamespace(
        git_commit=plan.source_commit,
        public_dict=lambda: {"git_commit": plan.source_commit},
    )

    monkeypatch.setitem(SCRIPT_GLOBALS, "detect_source_identity", lambda *a, **k: source)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_published_source", lambda *a: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_read_experiment_plan", lambda *a: plan)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_require_current_plan_files", lambda value: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_require_upstream_plan_bindings", lambda *a: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_revalidate_after_claim", lambda *a: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "load_battle_model_artifact", lambda path: base_model)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "build_runtime_identity",
        lambda: SimpleNamespace(sha256=plan.runtime_identity_sha256),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_pyboy_import_origins", lambda value: None)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "goal_manager_development_numpy_runtime_sha256",
        lambda: plan.numpy_runtime_sha256,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "battle_outcome_controller_timing_sha256",
        lambda: plan.controller_timing_sha256,
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "resolve_rom_path", lambda path: Path("red.gb"))
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "verify_rom",
        lambda path: SimpleNamespace(sha256=plan.rom_sha256),
    )

    def open_capture(state, manifest):  # type: ignore[no-untyped-def]
        del manifest
        name = Path(state).name
        opened.append(name)
        return train_capture if name.startswith("train") else development_capture

    monkeypatch.setitem(SCRIPT_GLOBALS, "open_battle_scenario_capture", open_capture)
    monkeypatch.setitem(SCRIPT_GLOBALS, "open_private_root", lambda *a, **k: store)
    monkeypatch.setitem(SCRIPT_GLOBALS, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "claim_first_pair_registry",
        lambda path: ClaimTransaction(claims),
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "read_root_pair_claim",
        lambda registry, claim_sha256: claims[claim_sha256],
    )

    def collect(capture, **kwargs):  # type: ignore[no-untyped-def]
        for index in range(2):
            kwargs["candidate_claim_sink"](index)
            kwargs["outcome_sink"](index, outcomes[index])
        return train_collection if capture is train_capture else development_collection

    monkeypatch.setitem(SCRIPT_GLOBALS, "collect_red_battle_outcome_example", collect)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "adapt_mlp_last_layer_from_outcomes",
        lambda *a, **k: update,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "prepare_red_battle_outcome_capture",
        lambda capture, **kwargs: SimpleNamespace(
            initial_observation_sha256=(
                plan.train.initial_observation_sha256
                if capture is train_capture
                else plan.development.initial_observation_sha256
            ),
            features=features,
        ),
    )

    def evaluation(model, examples):  # type: ignore[no-untyped-def]
        del examples
        choice = model.predict(
            features.candidate_vectors,
            legal_mask=features.legal_mask,
            current_pp=features.current_pp,
        )
        best = max(utilities)
        return SimpleNamespace(
            model_sha256=_sha(model),
            example_count=1,
            correct_preferences=int(utilities[choice] == best),
            root_lineage_ids=(plan.development.root_lineage_id,),
            public_dict=lambda: {"model_sha256": _sha(model)},
        )

    paired = SimpleNamespace(
        base_model_sha256=plan.base_model_sha256,
        updated_model_sha256=updated_sha256,
        example_count=1,
        updated_wins=updated_wins,
        base_wins=base_wins,
        equivalent_choices=int(updated_wins + base_wins == 0),
        discordant_examples=updated_wins + base_wins,
        base_correct_preferences=int(utilities[1] == max(utilities)),
        updated_correct_preferences=int(utilities[0] == max(utilities)),
        root_lineage_ids=(plan.development.root_lineage_id,),
        public_dict=lambda: {
            "updated_wins": updated_wins,
            "base_wins": base_wins,
            "discordant_examples": updated_wins + base_wins,
        },
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "evaluate_battle_outcome_preferences", evaluation)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "compare_battle_outcome_preferences",
        lambda *a, **k: paired,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "BattleOutcomeLearningCycle",
        lambda **kwargs: SimpleNamespace(public_dict=lambda: {"cycle": "ok"}),
    )

    args = SimpleNamespace(
        rom=None,
        private_root=Path("private"),
        plan=Path("plan.json"),
        expected_plan_sha256=plan.plan_sha256,
        base_model=Path("base/model.jsonl"),
        expected_base_model_sha256=plan.base_model_sha256,
        context_catalog=Path("context-catalog.json"),
        train_state=Path("train.state"),
        train_manifest=Path("train.state.json"),
        development_state=Path("development.state"),
        development_manifest=Path("development.state.json"),
    )
    return SCRIPT["_run"](args), store.writer, opened


def _record_types(writer: Writer) -> list[str]:
    return [record["record_type"] for _, record in writer.records]


def test_cycle_claims_every_candidate_and_types_a_descriptive_advantage(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    receipt, writer, opened = _exercise(
        monkeypatch,
        train_informative=True,
        development_informative=True,
    )

    assert receipt["status"] == "candidate_advantage_observed"
    assert receipt["root_claims_created"] == 2
    assert receipt["candidate_claims_created"] == 4
    assert receipt["measured_candidate_outcomes"] == 4
    assert receipt["activated_candidate_targets"] == 4
    assert receipt["deferred_unactivated_development_candidates"] == 0
    assert receipt["development_outcomes_opened"] == 2
    assert receipt["unexecuted_counterfactual_targets"] == 0
    assert receipt["unmeasured_action_targets"] == 0
    assert receipt["unseen_comparisons"] == 0
    assert receipt["historically_untouched_claimed"] is False
    assert opened == ["train.state", "development.state"]
    assert all(writer.durable)
    types = _record_types(writer)
    assert types.index("battle_outcome_root_pair_claim") < types.index(
        "battle_candidate_claim"
    )
    assert types.index("battle_model_candidate") < types.index(
        "battle_development_prediction_commitment"
    )
    for index, record_type in enumerate(types):
        if record_type == "battle_candidate_outcome":
            assert types[index - 1] == "battle_candidate_claim"
    terminal = writer.records[-1][1]
    assert terminal["record_type"] == "battle_outcome_cycle_terminal"
    recovered_public = dict(terminal)
    del recovered_public["record_type"]
    assert recovered_public == {
        key: value
        for key, value in receipt.items()
        if key not in {"schema", "artifact"}
    }


def test_flat_train_never_claims_or_executes_development(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    receipt, writer, opened = _exercise(
        monkeypatch,
        train_informative=False,
        development_informative=True,
    )

    assert receipt["status"] == "no_update"
    assert receipt["root_claims_created"] == 1
    assert receipt["model_sha256"] is None
    assert receipt["development_capture_metadata_opened"] is True
    assert receipt["development_outcomes_opened"] == 0
    assert receipt["activated_candidate_targets"] == 2
    assert receipt["deferred_unactivated_development_candidates"] == 2
    assert receipt["development_comparisons"] == 0
    assert opened == ["train.state", "development.state"]
    assert _record_types(writer)[-2:] == [
        "battle_outcome_no_update",
        "battle_outcome_cycle_terminal",
    ]
    assert _record_types(writer).count("battle_outcome_root_pair_claim") == 1


def test_development_flatness_does_not_influence_the_train_fit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    receipt, writer, _ = _exercise(
        monkeypatch,
        train_informative=True,
        development_informative=False,
    )

    assert receipt["model_fits"] == 1
    assert receipt["development_influenced_fit"] is False
    assert _record_types(writer).index("battle_model_candidate") < _record_types(
        writer
    ).index("battle_development_prediction_commitment")


def test_zero_discordance_is_an_explicit_rejection(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    receipt, _, _ = _exercise(
        monkeypatch,
        train_informative=True,
        development_informative=True,
        updated_wins=0,
        base_wins=0,
    )

    assert receipt["status"] == "rejected_no_development_discordance"
    assert receipt["candidate_advantage_observed"] is False


def test_paired_winner_cannot_disagree_with_committed_choices_and_outcomes() -> None:
    base_sha256 = "1" * 64
    updated_sha256 = "2" * 64
    root = "red-goal-root-" + "3" * 64
    outcomes = (
        SimpleNamespace(utility=1.0),
        SimpleNamespace(utility=0.0),
    )
    example = SimpleNamespace(root_lineage_id=root, outcomes=outcomes)
    base = SimpleNamespace(
        model_sha256=base_sha256,
        example_count=1,
        correct_preferences=0,
        root_lineage_ids=(root,),
    )
    updated = SimpleNamespace(
        model_sha256=updated_sha256,
        example_count=1,
        correct_preferences=1,
        root_lineage_ids=(root,),
    )
    forged = SimpleNamespace(
        base_model_sha256=base_sha256,
        updated_model_sha256=updated_sha256,
        example_count=1,
        updated_wins=0,
        base_wins=1,
        equivalent_choices=0,
        base_correct_preferences=0,
        updated_correct_preferences=1,
        root_lineage_ids=(root,),
    )

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleError"],
        match="evaluation identity differs",
    ):
        SCRIPT["_require_evaluation_identity"](
            base,
            updated,
            forged,
            base_model_sha256=base_sha256,
            updated_model_sha256=updated_sha256,
            development_example=example,
            base_choice=1,
            updated_choice=0,
        )


def test_development_capture_rejects_any_upstream_lineage_overlap() -> None:
    require = SCRIPT["_require_development_capture"]
    error = SCRIPT["BattleOutcomeCycleError"]
    commit = "a" * 40
    train = SimpleNamespace(
        manifest=SimpleNamespace(
            capture_id="train-capture",
            partition=ScenarioPartition.TRAIN,
            source_commit=commit,
            source_state_sha256="1" * 64,
            root_lineage_id="shared-lineage",
            state_sha256="2" * 64,
            initial_observation_sha256="3" * 64,
        )
    )
    development = SimpleNamespace(
        manifest=SimpleNamespace(
            capture_id="development-capture",
            partition=ScenarioPartition.DEVELOPMENT,
            source_commit=commit,
            source_state_sha256="4" * 64,
            root_lineage_id="shared-lineage",
            state_sha256="5" * 64,
            initial_observation_sha256="6" * 64,
        )
    )

    with pytest.raises(error, match="lineages overlap"):
        require(train, development, source_commit=commit)


def test_expected_base_digest_stops_before_private_capture_open(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    base_model = _model()
    plan = _plan(base_model)
    capture_opened = False

    def open_capture(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal capture_opened
        del args, kwargs
        capture_opened = True
        raise AssertionError("capture should remain unopened")

    source = SimpleNamespace(git_commit=plan.source_commit)
    monkeypatch.setitem(SCRIPT_GLOBALS, "detect_source_identity", lambda *a, **k: source)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_published_source", lambda *a: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_read_experiment_plan", lambda *a: plan)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_require_current_plan_files", lambda value: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_require_upstream_plan_bindings", lambda *a: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "open_battle_scenario_capture", open_capture)
    args = SimpleNamespace(
        plan=Path("plan.json"),
        expected_plan_sha256=plan.plan_sha256,
        expected_base_model_sha256="0" * 64,
        context_catalog=Path("context-catalog.json"),
    )

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleError"],
        match="expectation differs",
    ):
        SCRIPT["_run"](args)
    assert capture_opened is False


def test_development_choice_commitment_must_match_the_measured_example() -> None:
    require_commitment = SCRIPT["_require_committed_development_choices"]
    error = SCRIPT["BattleOutcomeCycleError"]
    model = _model()
    features = SimpleNamespace(
        candidate_vectors=(
            tuple(0.0 for _ in FEATURE_NAMES),
            tuple(1.0 for _ in FEATURE_NAMES),
        ),
        legal_mask=(True, True),
        current_pp=(10.0, 10.0),
    )
    example = SimpleNamespace(features=features, outcomes=(object(), object()))
    actual = model.predict(
        features.candidate_vectors,
        legal_mask=features.legal_mask,
        current_pp=features.current_pp,
    )

    with pytest.raises(error, match="pre-outcome commitment"):
        require_commitment(
            model,
            model,
            example,
            base_choice=1 - actual,
            updated_choice=actual,
        )


@pytest.mark.parametrize(
    "overrides",
    (
        {"menu_sha256": "9" * 64},
        {"hidden_embedding_sha256": "8" * 64},
        {
            "supported_candidate_count": 3,
            "distinct_candidate_vector_count": 3,
        },
        {
            "supported_candidate_count": 3,
            "distinct_hidden_embedding_count": 3,
        },
    ),
)
def test_execution_reauthenticates_every_frozen_menu_identity(
    overrides: dict[str, object],
) -> None:
    model = _model()
    plan = _plan(model)
    binding = replace(plan.train, **overrides)
    prepared = SimpleNamespace(
        initial_observation_sha256=plan.train.initial_observation_sha256,
        features=_features(),
    )

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleError"],
        match="prospective experiment",
    ):
        SCRIPT["_require_prepared_binding"](binding, prepared, model)


def test_candidate_claim_failure_prevents_controller_input(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    plan = _plan(_model())
    capture = _capture(plan.train)
    pair = SCRIPT["_root_pair"](plan, plan.train, stage="battle-train")
    controller_inputs = 0
    features = _features()

    class FailingWriter:
        def append(self, stream, record, *, durable=False):  # type: ignore[no-untyped-def]
            del record, durable
            if stream == "candidate_claims":
                raise OSError("fsync failed")

    def collect(capture, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal controller_inputs
        kwargs["candidate_claim_sink"](0)
        controller_inputs += 1
        raise AssertionError("controller input must remain unreachable")

    monkeypatch.setitem(SCRIPT_GLOBALS, "collect_red_battle_outcome_example", collect)
    with pytest.raises(OSError, match="fsync failed"):
        SCRIPT["_collect_claimed_capture"](
            FailingWriter(),
            plan=plan,
            capture_binding=plan.train,
            capture=capture,
            root_pair=pair,
            base_model=_model(),
            session_factory=lambda: None,
            prepared_boundary=SimpleNamespace(
                initial_observation_sha256=plan.train.initial_observation_sha256,
                features=features,
            ),
        )
    assert controller_inputs == 0


def test_forged_well_formed_plan_binding_cannot_pass_catalog_authentication() -> None:
    plan = _plan(_model())
    entry = SimpleNamespace(
        state_sha256=plan.train.source_state_sha256,
        slot_id=plan.train.source_slot_id,
        capture_id="upstream-capture",
        assignment_id=plan.train.source_assignment_id,
        context_id=plan.train.source_context_id,
        envelope_sha256=plan.train.source_envelope_sha256,
        authenticated_root_lineage_id=lambda **kwargs: plan.train.root_lineage_id,
    )
    catalog = SimpleNamespace(entries=(entry,))
    registry = SimpleNamespace(
        assignment=lambda slot_id: SimpleNamespace(
            partition="train",
            assignment_id=plan.train.source_assignment_id,
        )
    )
    forged_assignment = "f" * 64
    forged = replace(
        plan.train,
        source_assignment_id=forged_assignment,
        root_lineage_id=f"red-goal-root-{forged_assignment}",
    )

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleError"],
        match="catalog root",
    ):
        SCRIPT["_require_catalog_binding"](
            forged,
            expected_catalog_partition="train",
            catalog=catalog,
            registry=registry,
        )


def test_candidate_retention_must_cover_the_measured_menu(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    plan = _plan(_model())
    capture = _capture(plan.train)
    pair = SCRIPT["_root_pair"](plan, plan.train, stage="battle-train")
    outcome = SimpleNamespace(public_dict=lambda: {"utility": 1.0})
    features = _features()

    def collect(capture, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["candidate_claim_sink"](0)
        kwargs["outcome_sink"](0, outcome)
        return SimpleNamespace(
            outcomes=(outcome, outcome),
            initial_observation_sha256=plan.train.initial_observation_sha256,
            example=SimpleNamespace(features=features),
        )

    monkeypatch.setitem(SCRIPT_GLOBALS, "collect_red_battle_outcome_example", collect)
    with pytest.raises(
        SCRIPT["BattleOutcomeCycleError"],
        match="one exact menu",
    ):
        SCRIPT["_collect_claimed_capture"](
            Writer(),
            plan=plan,
            capture_binding=plan.train,
            capture=capture,
            root_pair=pair,
            base_model=_model(),
            session_factory=lambda: None,
            prepared_boundary=SimpleNamespace(
                initial_observation_sha256=plan.train.initial_observation_sha256,
                features=features,
            ),
        )


def test_retained_outcome_must_equal_the_outcome_used_for_fitting(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    plan = _plan(_model())
    capture = _capture(plan.train)
    pair = SCRIPT["_root_pair"](plan, plan.train, stage="battle-train")
    retained = SimpleNamespace(public_dict=lambda: {"utility": 1.0})
    returned = SimpleNamespace(public_dict=lambda: {"utility": -1.0})
    features = _features()

    def collect(capture, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["candidate_claim_sink"](0)
        kwargs["outcome_sink"](0, retained)
        kwargs["candidate_claim_sink"](1)
        kwargs["outcome_sink"](1, retained)
        return SimpleNamespace(
            outcomes=(returned, retained),
            initial_observation_sha256=plan.train.initial_observation_sha256,
            example=SimpleNamespace(features=features),
        )

    monkeypatch.setitem(SCRIPT_GLOBALS, "collect_red_battle_outcome_example", collect)
    with pytest.raises(
        SCRIPT["BattleOutcomeCycleError"],
        match="one exact menu",
    ):
        SCRIPT["_collect_claimed_capture"](
            Writer(),
            plan=plan,
            capture_binding=plan.train,
            capture=capture,
            root_pair=pair,
            base_model=_model(),
            session_factory=lambda: None,
            prepared_boundary=SimpleNamespace(
                initial_observation_sha256=plan.train.initial_observation_sha256,
                features=features,
            ),
        )
