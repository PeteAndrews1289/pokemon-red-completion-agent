from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from test_red_living_dex_option_adapter import (
    TARGETS,
    _budgets,
    _facts,
    _options,
    _prospects,
    _snapshot,
)

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_context_catalog import (
    parse_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexOptionKind,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.private_artifacts import (
    EpisodeWriter,
    PrivateArtifactError,
    PrivateArtifactRoot,
    initialize_private_root,
)
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedLivingDexAdaptedScenario,
    RedLivingDexOutcomeSnapshot,
    adapt_red_living_dex_options,
    bind_red_goal_option,
)
from pokemon_red_completion.red_living_dex_option_calibration import (
    build_red_living_dex_calibration_batch,
)
from pokemon_red_completion.red_living_dex_option_collector import (
    RedLivingDexBehaviorCommitment,
    RedLivingDexCollectionOrigin,
)
from pokemon_red_completion.red_living_dex_option_materializer import (
    RedLivingDexMaterializationDisposition,
    RedLivingDexMaterializationPlan,
    RedLivingDexMaterializationScenario,
    RedLivingDexMaterializationScenarioOrigin,
    RedLivingDexOptionMaterializerError,
    bind_red_living_dex_observer_provenance,
    bind_verified_red_living_dex_materialization_scenario,
    build_red_living_dex_materialization_plan,
    red_living_dex_verified_capture_scenario_identity,
    run_red_living_dex_materialization_plan,
)

_GOAL_KIND = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
}
_TRAIN_KINDS = (
    LivingDexOptionKind.ACQUIRE,
    LivingDexOptionKind.EVOLVE,
    LivingDexOptionKind.DEVELOP,
    LivingDexOptionKind.MANAGE_STORAGE,
    LivingDexOptionKind.ACQUIRE,
    LivingDexOptionKind.EVOLVE,
    LivingDexOptionKind.DEVELOP,
    LivingDexOptionKind.MANAGE_STORAGE,
)


def _make_store(tmp_path: Path) -> tuple[Path, PrivateArtifactRoot]:
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
    return root, store


def _adapted(
    index: int,
    *,
    kind: LivingDexOptionKind,
    family: str,
    location: str,
    execute_calls: list[tuple[int, int]],
    on_execute: Callable[[int, int], None] | None = None,
    scenario_identity_sha256: str | None = None,
) -> RedLivingDexAdaptedScenario:
    prospects = tuple(replace(item, kind=kind) for item in _prospects()[:3])
    options = []
    for option_index, prospect in enumerate(prospects):

        def execute(bound_index: int = option_index) -> GoalExecutionReport:
            if on_execute is not None:
                on_execute(index, bound_index)
            execute_calls.append((index, bound_index))
            return GoalExecutionReport(10 + bound_index, 100 + bound_index, {"bounded": True})

        binding = ExecutableGoalBinding(
            binding_ref=f"private.materializer.{index}.{option_index}",
            kind=_GOAL_KIND[kind],
            estimated_effort=0.2 + 0.1 * option_index,
            estimated_risk=0.1 * option_index,
            execute=execute,
            verify=lambda _report: GoalVerification.succeeded(),
        )
        options.append(
            bind_red_goal_option(
                binding,
                prospect,
                family_ref=f"private.family.{family}",
                location_ref=f"private.location.{location}",
                resource_pool_ref=(
                    "private.resource.capture"
                    if prospect.required_consumable_units > 0
                    else None
                ),
            )
        )
    # A complete menu may retain hard-masked work, but only authenticated
    # available rows can ever receive behavior probability.
    options.append(
        replace(
            _options(prefix=f"private.materializer.{index}.masked")[3],
            family_ref=f"private.family.{family}.masked",
            location_ref=f"private.location.{location}.masked",
        )
    )
    return adapt_red_living_dex_options(
        _snapshot(
            scenario=(
                f"{10_000 + index:064x}"
                if scenario_identity_sha256 is None
                else scenario_identity_sha256
            ),
            provenance=f"{20_000 + index:064x}",
        ),
        _facts(),
        _budgets(),
        tuple(options),
        ordering_seed_sha256=f"{30_000 + index:064x}",
    )


def _scenario(
    index: int,
    *,
    partition: str,
    kind: LivingDexOptionKind,
    family: str,
    location: str,
    execute_calls: list[tuple[int, int]],
    observer_calls: list[int],
    on_execute: Callable[[int, int], None] | None = None,
    observe_after: Callable[[], RedLivingDexOutcomeSnapshot] | None = None,
) -> RedLivingDexMaterializationScenario:
    adapted = _adapted(
        index,
        kind=kind,
        family=family,
        location=location,
        execute_calls=execute_calls,
        on_execute=on_execute,
    )

    def observe() -> RedLivingDexOutcomeSnapshot:
        observer_calls.append(index)
        if observe_after is not None:
            return observe_after()
        snapshot = _snapshot(
            species=(TARGETS[0], TARGETS[1]),
            scenario=adapted.before.scenario_identity_sha256,
            dependencies=3,
            consumables=8,
            health=70,
            irreversible=3,
            actions=350,
            frames=3_000,
            provenance=f"{40_000 + index:064x}",
        )
        return bind_red_living_dex_observer_provenance(
            snapshot,
            observer_binding_sha256=f"{50_000 + index:064x}",
        )

    return RedLivingDexMaterializationScenario(
        adapted,
        partition,
        f"{50_000 + index:064x}",
        observe,
    )


def _plan(
    *,
    execute_calls: list[tuple[int, int]] | None = None,
    observer_calls: list[int] | None = None,
    on_execute: Callable[[int, int], None] | None = None,
    first_observer: Callable[[], RedLivingDexOutcomeSnapshot] | None = None,
) -> RedLivingDexMaterializationPlan:
    executed = [] if execute_calls is None else execute_calls
    observed = [] if observer_calls is None else observer_calls
    scenarios = [
        _scenario(
            index,
            partition="train",
            kind=kind,
            family=f"train-{index % 3}",
            location=f"train-{index % 2}",
            execute_calls=executed,
            observer_calls=observed,
            on_execute=on_execute,
            observe_after=first_observer if index == 0 else None,
        )
        for index, kind in enumerate(_TRAIN_KINDS)
    ]
    scenarios.extend(
        _scenario(
            100 + index,
            partition="development",
            kind=(
                LivingDexOptionKind.ACQUIRE
                if index % 2 == 0
                else LivingDexOptionKind.EVOLVE
            ),
            family=f"development-{index}",
            location=f"development-{index}",
            execute_calls=executed,
            observer_calls=observed,
            on_execute=on_execute,
        )
        for index in range(4)
    )
    return build_red_living_dex_materialization_plan(scenarios)


def test_plan_freezes_minimum_coverage_without_private_identity_leakage() -> None:
    plan = _plan()
    public = plan.public_dict()

    assert public["partition_counts"] == {"development": 4, "train": 8}
    assert public["train_offered_option_kind_count"] == 4
    assert public["train_family_count"] == 3
    assert public["development_family_count"] == 4
    assert public["development_location_count"] == 4
    assert public["family_overlap"] == 0
    assert public["location_overlap"] == 0
    assert public["claim_before_randomization"] is True
    assert public["verified_capture_plan"] is False
    assert public["scenario_origin"] == "synthetic-rehearsal"
    encoded = json.dumps(public, sort_keys=True).lower()
    assert "private." not in encoded
    assert plan.scenarios[0].scenario_identity_sha256 not in encoded


def test_verified_capture_factory_binds_exact_state_envelope_and_attestation() -> None:
    state = b"verified-repeatable-red-capture"
    envelope = (
        json.dumps(
            {
                "checkpoint_id": "living-dex-repeatable-fixture",
                "checkpoint_label": "Living Dex repeatable fixture",
                "checkpoints_completed": 4,
                "checkpoints_total": 36,
                "schema": "pokemon-private-captured-progress-v1",
                "state_sha256": hashlib.sha256(state).hexdigest(),
                "verified_objective_ids": ["power_on"],
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    capture = parse_goal_manager_context_capture(state, envelope)
    identity = red_living_dex_verified_capture_scenario_identity(capture)
    adapted = _adapted(
        900,
        kind=LivingDexOptionKind.ACQUIRE,
        family="verified",
        location="verified",
        execute_calls=[],
        scenario_identity_sha256=identity,
    )
    scenario = bind_verified_red_living_dex_materialization_scenario(
        capture,
        adapted,
        partition="train",
        observer_binding_sha256="a" * 64,
        checkpoint_attestation_sha256="b" * 64,
        observe_after=lambda: _snapshot(scenario=identity),
    )

    assert scenario.scenario_origin is (
        RedLivingDexMaterializationScenarioOrigin.VERIFIED_REPEATABLE_CAPTURE
    )
    assert scenario.checkpoint_binding_sha256 is not None
    assert scenario.checkpoint_attestation_sha256 == "b" * 64
    assert scenario.public_dict()["verified_repeatable_capture"] is True
    with pytest.raises(RedLivingDexOptionMaterializerError, match="mixes rehearsal"):
        RedLivingDexMaterializationPlan((scenario, *_plan().scenarios[1:]))
    with pytest.raises(RedLivingDexOptionMaterializerError, match="checkpoint bytes"):
        bind_verified_red_living_dex_materialization_scenario(
            capture,
            _adapted(
                901,
                kind=LivingDexOptionKind.ACQUIRE,
                family="wrong",
                location="wrong",
                execute_calls=[],
            ),
            partition="train",
            observer_binding_sha256="a" * 64,
            checkpoint_attestation_sha256="b" * 64,
            observe_after=lambda: _snapshot(),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("short_train", "eight train"),
        ("short_development", "four development"),
        ("duplicate", "repeats a scenario"),
        ("few_kinds", "four genuine train option kinds"),
        ("few_train_families", "three train transformation families"),
        ("few_development_families", "four development transformation families"),
        ("few_development_locations", "four development locations"),
        ("family_overlap", "families overlap"),
        ("location_overlap", "locations overlap"),
    ),
)
def test_plan_rejects_each_coverage_or_partition_mutation(
    mutation: str,
    message: str,
) -> None:
    base = list(_plan().scenarios)
    if mutation == "short_train":
        base.pop(0)
    elif mutation == "short_development":
        base.pop()
    elif mutation == "duplicate":
        base[-1] = base[0]
    elif mutation == "few_kinds":
        base = [
            _scenario(
                index if item.partition == "train" else 100 + index,
                partition=item.partition,
                kind=(
                    LivingDexOptionKind.ACQUIRE
                    if item.partition == "train"
                    else item.adapted.menu.candidates[
                        item.adapted.menu.available_indices[0]
                    ].features.kind
                ),
                family=(
                    f"train-{index % 3}"
                    if item.partition == "train"
                    else f"development-{index}"
                ),
                location=(
                    f"train-{index % 2}"
                    if item.partition == "train"
                    else f"development-{index}"
                ),
                execute_calls=[],
                observer_calls=[],
            )
            for index, item in enumerate(base)
        ]
    elif mutation == "few_train_families":
        for item in base:
            if item.partition == "train":
                for option in item.adapted.ordered_options:
                    object.__setattr__(
                        option,
                        "family_ref",
                        "private.family.train-one",
                    )
    elif mutation in {
        "few_development_families",
        "few_development_locations",
        "family_overlap",
        "location_overlap",
    }:
        train_family = base[0].adapted.ordered_options[
            base[0].adapted.menu.available_indices[0]
        ].family_ref
        train_location = base[0].adapted.ordered_options[
            base[0].adapted.menu.available_indices[0]
        ].location_ref
        changed = []
        overlap_mutated = False
        for item in base:
            if item.partition != "development":
                changed.append(item)
                continue
            for option in item.adapted.ordered_options:
                if mutation == "family_overlap" and not overlap_mutated:
                    object.__setattr__(option, "family_ref", train_family)
                elif mutation == "few_development_families":
                    object.__setattr__(
                        option,
                        "family_ref",
                        "private.family.development-one",
                    )
                if mutation == "location_overlap" and not overlap_mutated:
                    object.__setattr__(option, "location_ref", train_location)
                elif mutation == "few_development_locations":
                    object.__setattr__(
                        option,
                        "location_ref",
                        "private.location.development-one",
                    )
            changed.append(item)
            if mutation in {"family_overlap", "location_overlap"}:
                overlap_mutated = True
        base = changed
    with pytest.raises(RedLivingDexOptionMaterializerError, match=message):
        RedLivingDexMaterializationPlan(tuple(base))


def test_materializer_claims_then_persists_one_selection_before_each_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, store = _make_store(tmp_path)
    execute_calls: list[tuple[int, int]] = []
    observer_calls: list[int] = []
    selections_persisted = 0
    issued: list[str] = []
    real_append = EpisodeWriter.append
    real_issue = __import__(
        "pokemon_red_completion.red_living_dex_option_materializer",
        fromlist=["issue_red_living_dex_behavior_commitment"],
    ).issue_red_living_dex_behavior_commitment

    def append(
        writer: EpisodeWriter,
        stream: str,
        record: dict[str, object],
        *,
        durable: bool = False,
    ) -> None:
        nonlocal selections_persisted
        real_append(writer, stream, record, durable=durable)
        if stream == "selection":
            assert durable is True
            selections_persisted += 1

    def issue(
        adapted: RedLivingDexAdaptedScenario,
        *,
        partition: str,
    ) -> RedLivingDexBehaviorCommitment:
        assert store.inspect_episode_state(
            f"redldx-{adapted.before.scenario_identity_sha256}"
        ).status == "partial"
        issued.append(adapted.before.scenario_identity_sha256)
        return real_issue(adapted, partition=partition)

    monkeypatch.setattr(EpisodeWriter, "append", append)
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_option_materializer.issue_red_living_dex_behavior_commitment",
        issue,
    )

    def on_execute(_scenario: int, _option: int) -> None:
        assert selections_persisted == len(issued)

    plan = _plan(
        execute_calls=execute_calls,
        observer_calls=observer_calls,
        on_execute=on_execute,
    )
    result = run_red_living_dex_materialization_plan(store, plan)

    assert len(issued) == 12
    assert selections_persisted == 12
    assert len(execute_calls) == 12
    assert len(observer_calls) == 12
    assert len(result.examples) == 12
    assert all(item.newly_executed for item in result.receipts)
    assert all(item.settled for item in result.receipts)
    assert all(
        item.disposition is RedLivingDexMaterializationDisposition.EXECUTED_SETTLED
        for item in result.receipts
    )
    assert all(
        sum(option.consumed for option in item.scenario.adapted.ordered_options) == 1
        for item in result.receipts
    )
    for scenario in plan.scenarios:
        reader = store.open_episode(scenario.episode_id)
        assert reader.stream_names == (
            "claim",
            "observation",
            "outcome",
            "selection",
        )
        assert reader.summary.stream_records == (
            ("claim", 1),
            ("observation", 1),
            ("outcome", 1),
            ("selection", 1),
        )


def test_completed_plan_reloads_exact_examples_without_reissue_or_reexecution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, store = _make_store(tmp_path)
    execute_calls: list[tuple[int, int]] = []
    observer_calls: list[int] = []
    plan = _plan(execute_calls=execute_calls, observer_calls=observer_calls)
    first = run_red_living_dex_materialization_plan(store, plan)
    first_private = [item.private_dict() for item in first.examples]

    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_option_materializer.issue_red_living_dex_behavior_commitment",
        lambda *_args, **_kwargs: pytest.fail("commitment was reissued"),
    )
    replay = run_red_living_dex_materialization_plan(store, plan)

    assert execute_calls and len(execute_calls) == 12
    assert observer_calls and len(observer_calls) == 12
    assert [item.private_dict() for item in replay.examples] == first_private
    assert all(not item.newly_executed for item in replay.receipts)
    assert all(
        item.disposition is RedLivingDexMaterializationDisposition.RECOVERED_COMPLETE
        for item in replay.receipts
    )
    assert replay.public_dict()["new_controller_authority_crossings"] == 0


def test_completed_plan_reloads_from_fresh_process_objects_without_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, store = _make_store(tmp_path)
    first_execute_calls: list[tuple[int, int]] = []
    first_observer_calls: list[int] = []
    first_plan = _plan(
        execute_calls=first_execute_calls,
        observer_calls=first_observer_calls,
    )
    first = run_red_living_dex_materialization_plan(store, first_plan)

    resumed_execute_calls: list[tuple[int, int]] = []
    resumed_observer_calls: list[int] = []
    reconstructed_plan = _plan(
        execute_calls=resumed_execute_calls,
        observer_calls=resumed_observer_calls,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_option_materializer.issue_red_living_dex_behavior_commitment",
        lambda *_args, **_kwargs: pytest.fail("commitment was reissued"),
    )

    resumed = run_red_living_dex_materialization_plan(store, reconstructed_plan)

    assert first_execute_calls and len(first_execute_calls) == 12
    assert first_observer_calls and len(first_observer_calls) == 12
    assert resumed_execute_calls == []
    assert resumed_observer_calls == []
    assert [item.private_dict() for item in resumed.examples] == [
        item.private_dict() for item in first.examples
    ]
    assert all(
        receipt.disposition
        is RedLivingDexMaterializationDisposition.RECOVERED_COMPLETE
        for receipt in resumed.receipts
    )


def test_completed_episode_tampering_fails_closed_without_a_new_issuance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    execute_calls: list[tuple[int, int]] = []
    observer_calls: list[int] = []
    plan = _plan(execute_calls=execute_calls, observer_calls=observer_calls)
    run_red_living_dex_materialization_plan(store, plan)
    executed_before_reload = tuple(execute_calls)
    observed_before_reload = tuple(observer_calls)

    outcome = root / plan.scenarios[0].episode_id / "outcome.jsonl"
    outcome.write_bytes(b'{"tampered":true}\n')
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_option_materializer.issue_red_living_dex_behavior_commitment",
        lambda *_args, **_kwargs: pytest.fail("commitment was reissued"),
    )

    with pytest.raises(
        RedLivingDexOptionMaterializerError,
        match="episode cannot be authenticated",
    ):
        run_red_living_dex_materialization_plan(store, plan)

    assert tuple(execute_calls) == executed_before_reload
    assert tuple(observer_calls) == observed_before_reload


def test_process_interruption_is_failed_once_and_never_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, store = _make_store(tmp_path)
    execute_calls: list[tuple[int, int]] = []
    observer_calls: list[int] = []
    interrupted = False
    issues = 0

    def interrupt_once(_scenario: int, _option: int) -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt

    plan = _plan(
        execute_calls=execute_calls,
        observer_calls=observer_calls,
        on_execute=interrupt_once,
    )
    real_issue = __import__(
        "pokemon_red_completion.red_living_dex_option_materializer",
        fromlist=["issue_red_living_dex_behavior_commitment"],
    ).issue_red_living_dex_behavior_commitment

    def issue(*args: object, **kwargs: object) -> RedLivingDexBehaviorCommitment:
        nonlocal issues
        issues += 1
        return real_issue(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_option_materializer.issue_red_living_dex_behavior_commitment",
        issue,
    )

    with pytest.raises(KeyboardInterrupt):
        run_red_living_dex_materialization_plan(store, plan)

    assert issues == 1
    assert execute_calls == []
    assert observer_calls == []
    assert store.inspect_episode_state(plan.scenarios[0].episode_id).status == "failed"

    resumed = run_red_living_dex_materialization_plan(store, plan)

    assert resumed.receipts[0].disposition is (
        RedLivingDexMaterializationDisposition.SKIPPED_FAILED
    )
    assert resumed.receipts[0].state.reason_code == "unhandled_exception"
    assert issues == 12
    assert len(execute_calls) == 11
    assert len(observer_calls) == 11


def test_receipt_rejects_execution_flag_or_disposition_overclaim(tmp_path: Path) -> None:
    _root, store = _make_store(tmp_path)
    receipt = run_red_living_dex_materialization_plan(store, _plan()).receipts[0]

    with pytest.raises(
        RedLivingDexOptionMaterializerError,
        match="complete disposition differs",
    ):
        replace(receipt, newly_executed=False)
    with pytest.raises(
        RedLivingDexOptionMaterializerError,
        match="complete disposition differs",
    ):
        replace(
            receipt,
            disposition=RedLivingDexMaterializationDisposition.EXECUTED_CENSORED,
        )


def test_durable_rom_free_rehearsal_cannot_open_authentic_calibration(
    tmp_path: Path,
) -> None:
    _root, store = _make_store(tmp_path)
    result = run_red_living_dex_materialization_plan(store, _plan())
    batch = build_red_living_dex_calibration_batch(result.examples)

    assert all(
        example.collection_origin is RedLivingDexCollectionOrigin.DURABLE_REHEARSAL
        for example in result.examples
    )
    assert batch.fit_ready is False
    assert batch.public_dict()["durable_materialization_counts"] == {
        "development": 0,
        "train": 0,
    }


def test_orphan_claim_is_interrupted_and_only_never_claimed_scenarios_continue(
    tmp_path: Path,
) -> None:
    _root, store = _make_store(tmp_path)
    execute_calls: list[tuple[int, int]] = []
    observer_calls: list[int] = []
    plan = _plan(execute_calls=execute_calls, observer_calls=observer_calls)
    store.begin_episode(plan.scenarios[0].episode_id)

    result = run_red_living_dex_materialization_plan(store, plan)

    assert result.receipts[0].disposition is (
        RedLivingDexMaterializationDisposition.SKIPPED_INTERRUPTED
    )
    assert result.receipts[0].example is None
    assert result.receipts[0].state.reason_code == "process_interrupted"
    assert len(execute_calls) == 11
    assert len(observer_calls) == 11
    assert len(result.examples) == 11
    assert (0, 0) not in execute_calls


def test_selection_persistence_failure_consumes_scenario_without_execution_or_reissue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, store = _make_store(tmp_path)
    execute_calls: list[tuple[int, int]] = []
    observer_calls: list[int] = []
    plan = _plan(execute_calls=execute_calls, observer_calls=observer_calls)
    real_append = EpisodeWriter.append
    issues = 0

    def append(
        writer: EpisodeWriter,
        stream: str,
        record: dict[str, object],
        *,
        durable: bool = False,
    ) -> None:
        if stream == "selection":
            raise PrivateArtifactError("simulated selection sync failure")
        real_append(writer, stream, record, durable=durable)

    real_issue = __import__(
        "pokemon_red_completion.red_living_dex_option_materializer",
        fromlist=["issue_red_living_dex_behavior_commitment"],
    ).issue_red_living_dex_behavior_commitment

    def issue(*args: object, **kwargs: object) -> RedLivingDexBehaviorCommitment:
        nonlocal issues
        issues += 1
        return real_issue(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(EpisodeWriter, "append", append)
    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_option_materializer.issue_red_living_dex_behavior_commitment",
        issue,
    )
    with pytest.raises(PrivateArtifactError, match="selection sync failure"):
        run_red_living_dex_materialization_plan(store, plan)

    assert issues == 1
    assert execute_calls == []
    assert observer_calls == []
    assert store.inspect_episode_state(plan.scenarios[0].episode_id).status == "failed"

    monkeypatch.setattr(EpisodeWriter, "append", real_append)
    result = run_red_living_dex_materialization_plan(store, plan)
    assert result.receipts[0].disposition is (
        RedLivingDexMaterializationDisposition.SKIPPED_FAILED
    )
    assert issues == 12
    assert len(execute_calls) == 11


def test_unbound_after_observation_is_censored_and_never_becomes_a_target(
    tmp_path: Path,
) -> None:
    _root, store = _make_store(tmp_path)

    def wrong_scenario() -> RedLivingDexOutcomeSnapshot:
        snapshot = _snapshot(
            species=(TARGETS[0], TARGETS[1]),
            scenario="f" * 64,
            dependencies=3,
            consumables=8,
            health=70,
            irreversible=3,
            actions=350,
            frames=3_000,
            provenance="e" * 64,
        )
        return bind_red_living_dex_observer_provenance(
            snapshot,
            observer_binding_sha256=f"{50_000:064x}",
        )

    plan = _plan(first_observer=wrong_scenario)
    result = run_red_living_dex_materialization_plan(store, plan)
    first = result.receipts[0]

    assert first.disposition is RedLivingDexMaterializationDisposition.EXECUTED_CENSORED
    assert first.example is not None
    assert first.example.example.outcome.status is LivingDexOutcomeStatus.CENSORED
    assert first.example.example.outcome.censor_reason is (
        LivingDexCensorReason.PROVENANCE_FAILED
    )
    assert first.example.example.outcome.target_vector is None
    assert first.public_dict()["target_recorded"] is False


def test_observer_provenance_not_derived_from_binding_is_target_free(
    tmp_path: Path,
) -> None:
    _root, store = _make_store(tmp_path)

    def unbound_receipt() -> RedLivingDexOutcomeSnapshot:
        return _snapshot(
            species=(TARGETS[0], TARGETS[1]),
            scenario=f"{10_000:064x}",
            dependencies=3,
            consumables=8,
            health=70,
            irreversible=3,
            actions=350,
            frames=3_000,
            provenance="d" * 64,
        )

    result = run_red_living_dex_materialization_plan(
        store,
        _plan(first_observer=unbound_receipt),
    )
    first = result.receipts[0]

    assert first.example is not None
    assert first.example.example.outcome.status is LivingDexOutcomeStatus.CENSORED
    assert first.example.example.outcome.censor_reason is (
        LivingDexCensorReason.OBSERVATION_FAILED
    )
    assert first.example.after_observer_provenance_sha256 is None
    assert first.example.example.outcome.target_vector is None
    reader = store.open_episode(first.scenario.episode_id)
    observation = next(reader.iter_stream("observation", max_records=1))
    assert observation["after_observation_recorded"] is False
    assert observation["snapshot_provenance_payload"] is None


def test_synthetic_available_executor_is_rejected_before_any_claim(tmp_path: Path) -> None:
    _root, store = _make_store(tmp_path)
    adapted = adapt_red_living_dex_options(
        _snapshot(scenario="d" * 64),
        _facts(),
        _budgets(),
        _options(prefix="private.synthetic"),
        ordering_seed_sha256="c" * 64,
    )
    with pytest.raises(RedLivingDexOptionMaterializerError, match="synthetic available"):
        RedLivingDexMaterializationScenario(
            adapted,
            "train",
            "b" * 64,
            lambda: _snapshot(scenario="d" * 64),
        )
    assert store.inspect_episode_state(f"redldx-{'d' * 64}").status == "absent"


def test_same_scenario_cannot_retry_under_a_changed_menu_or_partition(
    tmp_path: Path,
) -> None:
    _root, store = _make_store(tmp_path)
    plan = _plan()
    fresh = _plan()
    original = fresh.scenarios[0]
    replacement_adapted = adapt_red_living_dex_options(
        original.adapted.before,
        original.adapted.facts,
        original.adapted.budgets,
        tuple(reversed(original.adapted.ordered_options)),
        ordering_seed_sha256="a" * 64,
    )
    changed = replace(original, adapted=replacement_adapted)
    changed_plan = RedLivingDexMaterializationPlan((changed, *fresh.scenarios[1:]))
    run_red_living_dex_materialization_plan(store, plan)

    with pytest.raises(
        RedLivingDexOptionMaterializerError,
        match="claim differs from the frozen scenario",
    ):
        run_red_living_dex_materialization_plan(store, changed_plan)
