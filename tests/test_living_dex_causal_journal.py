from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from pokemon_red_completion.living_dex_causal_journal import (
    LIVING_DEX_CAUSAL_COLLECTION_ID,
    LivingDexCausalDisposition,
    LivingDexCausalEffectCheckpoint,
    LivingDexCausalIdentity,
    LivingDexCausalJournalError,
    LivingDexCausalObservation,
    LivingDexCausalResolvedArm,
    LivingDexCausalScenario,
    LivingDexControllerGate,
    load_living_dex_authenticated_causal_examples,
    materialize_living_dex_causal_example,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexObservedOutcome,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionUnavailableReason,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
    initialize_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _store_and_registry(tmp_path: Path) -> tuple[PrivateArtifactRoot, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    registry = tmp_path / "claims"
    repository.mkdir()
    root.mkdir()
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    return (
        initialize_private_root(
            root,
            repository_root=repository,
            device_id=device_id,
            git_worktree_probe=lambda _path: False,
        ),
        registry,
    )


def _features(kind: LivingDexOptionKind, offset: float) -> LivingDexOptionFeatures:
    return LivingDexOptionFeatures(
        kind,
        completion_gain=0.8 - offset,
        dependency_unlock_gain=0.4 + offset,
        travel_effort=0.2 + offset,
        execution_effort=0.3 + offset,
        resource_cost=0.1,
        storage_cost=0.1,
        party_risk=0.1 + offset,
        irreversibility_risk=0.0,
        uncertainty=0.2,
    )


def _menu(prefix: str) -> LivingDexOptionMenu:
    context = LivingDexOptionContext(0.8, 0.6, 0.5, 0.3, 0.2, 0.4, 0.5)
    return LivingDexOptionMenu(
        context,
        (
            LivingDexOptionCandidate(
                f"{prefix}.capture",
                _features(LivingDexOptionKind.ACQUIRE, 0.0),
                LivingDexOptionAvailability.AVAILABLE,
            ),
            LivingDexOptionCandidate(
                f"{prefix}.evolve",
                _features(LivingDexOptionKind.EVOLVE, 0.1),
                LivingDexOptionAvailability.AVAILABLE,
            ),
            LivingDexOptionCandidate(
                f"{prefix}.trade",
                _features(LivingDexOptionKind.TRADE, 0.15),
                LivingDexOptionAvailability.UNAVAILABLE,
                LivingDexOptionUnavailableReason.MISSING_CAPABILITY,
            ),
        ),
    )


@dataclass
class _Meter:
    binding_sha256: str
    recovery_instance_sha256: str
    controller_actions: int = 0
    emulator_frames: int = 0

    def checkpoint(self) -> LivingDexCausalEffectCheckpoint:
        return LivingDexCausalEffectCheckpoint(
            self.controller_actions,
            self.emulator_frames,
        )


@dataclass
class _Harness:
    meter: _Meter
    resolver_calls: list[int]
    executions: list[int]
    observations: list[str]
    trace: dict[str, object]


def _scenario(
    label: str,
    *,
    lineage: str | None = None,
    state: str | None = None,
    envelope: str | None = None,
    title_shape: str = "red-shaped",
    resolver_failure: bool = False,
) -> tuple[LivingDexCausalScenario, _Harness]:
    menu = _menu(f"private.{label}")
    bindings = tuple(_sha((label, candidate.binding_ref)) for candidate in menu.candidates)
    origin = {
        "collection_pressure": 0.8,
        "shape": title_shape,
        "world_state": {"party_slots": 6},
    }
    meter = _Meter(
        _sha((label, "meter")),
        _sha((label, "meter-instance")),
    )
    harness = _Harness(meter, [], [], [], {"actions": []})
    identity = LivingDexCausalIdentity(
        source_commit="a" * 40,
        partition="train",
        lineage_sha256=_sha((label, "lineage")) if lineage is None else lineage,
        setup_terminal_sha256=_sha((label, "terminal")),
        setup_pair_claim_sha256=_sha((label, "setup-claim")),
        setup_attestation_sha256=_sha((label, "attestation")),
        state_sha256=_sha((label, "state")) if state is None else state,
        envelope_sha256=_sha((label, "envelope")) if envelope is None else envelope,
        menu_sha256=menu.policy_sha256,
        binding_roster_sha256=canonical_sha256(
            {
                "binding_sha256s": list(bindings),
                "schema": "pokemon.core.living-dex-causal-binding-roster.v1",
            }
        ),
        origin_observation_sha256=canonical_sha256(origin),
        observer_binding_sha256=_sha((label, "observer")),
        effect_meter_binding_sha256=meter.binding_sha256,
        runner_sha256=_sha((label, "runner")),
    )

    @contextmanager
    def resolve_selected(
        index: int,
        gate: LivingDexControllerGate,
    ) -> Iterator[LivingDexCausalResolvedArm]:
        harness.resolver_calls.append(index)
        assert not gate.released
        if resolver_failure:
            raise RuntimeError("injected resolver failure")

        def execute(controller_gate: LivingDexControllerGate) -> None:
            controller_gate.require_released()
            harness.executions.append(index)
            harness.meter.controller_actions += 3
            harness.meter.emulator_frames += 12
            harness.trace = {"actions": ["a", "left", "a"], "selected": index}

        yield LivingDexCausalResolvedArm(
            bindings[index],
            harness.meter,
            execute,
            lambda: harness.trace,
        )

    def observe_after() -> LivingDexCausalObservation:
        harness.observations.append("observed")
        return LivingDexCausalObservation(
            LivingDexObservedOutcome(
                LivingDexOutcomeStatus.SETTLED,
                verified_success=True,
                completion_gain=0.5,
                dependency_unlock_gain=0.25,
                action_cost=0.03,
                frame_cost=0.12,
                resource_cost=0.0,
                party_cost=0.0,
                storage_cost=0.1,
                irreversible_loss=0.0,
            ),
            {"ledger_before": 40, "ledger_after": 41, "schema": "test-observer-v1"},
        )

    return (
        LivingDexCausalScenario(
            identity,
            menu,
            bindings,
            origin,
            meter,
            resolve_selected,
            observe_after,
        ),
        harness,
    )


def test_settled_selected_arm_round_trips_without_a_second_execution(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario("settled")

    receipt = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )
    assert receipt.disposition is LivingDexCausalDisposition.EXECUTED_SETTLED
    assert receipt.example is not None
    assert receipt.example.outcome.status is LivingDexOutcomeStatus.SETTLED
    assert receipt.public_dict()["causal_train_example_recorded"] is True
    assert receipt.example.menu.candidates[0].binding_ref == "policy-row-0"
    assert harness.resolver_calls == [receipt.example.selected_candidate_index]
    assert harness.executions == [receipt.example.selected_candidate_index]
    assert harness.observations == ["observed"]

    recovered = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )
    assert recovered.disposition is LivingDexCausalDisposition.RECOVERED_COMPLETE
    assert recovered.example == receipt.example
    assert harness.resolver_calls == [receipt.example.selected_candidate_index]
    assert harness.executions == [receipt.example.selected_candidate_index]


def test_complete_causal_example_family_reopens_with_all_private_joins(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, _ = _scenario("aggregate-reader")
    receipt = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )

    rows = load_living_dex_authenticated_causal_examples(store)

    assert len(rows) == 1
    assert rows[0].identity == scenario.identity
    assert rows[0].example == receipt.example
    assert rows[0].terminal == receipt.terminal
    assert not hasattr(rows[0], "public_dict")


def test_complete_causal_family_can_remain_locked_through_a_consumer(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, _ = _scenario("aggregate-reader-held-lock")
    receipt = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )

    with store.collection_session(LIVING_DEX_CAUSAL_COLLECTION_ID) as session:
        rows = load_living_dex_authenticated_causal_examples(
            store,
            collection_session=session,
        )
        session.require_store(store)

    assert len(rows) == 1
    assert rows[0].example == receipt.example


def test_causal_corpus_reader_fails_closed_on_example_without_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, _ = _scenario("aggregate-reader-interrupted")

    def interrupt(stage: str) -> None:
        if stage == "after_example_publish":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        materialize_living_dex_causal_example(
            scenario,
            store=store,
            claim_registry=registry,
            failpoint=interrupt,
        )

    find_record = PrivateArtifactRoot.find_sealed_record

    def hide_terminal(
        private_store: PrivateArtifactRoot,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ) -> PrivateSealedRecord | None:
        if record_id.startswith("lc-terminal-"):
            return None
        return find_record(
            private_store,
            record_id,
            expected_kind=expected_kind,
        )

    monkeypatch.setattr(PrivateArtifactRoot, "find_sealed_record", hide_terminal)

    with pytest.raises(LivingDexCausalJournalError, match="required causal record"):
        load_living_dex_authenticated_causal_examples(store)


def test_one_preinput_failure_reuses_selection_then_second_failure_is_terminal(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    first, first_harness = _scenario("retry", resolver_failure=True)
    receipt = materialize_living_dex_causal_example(
        first,
        store=store,
        claim_registry=registry,
    )
    assert receipt.retry_allowed
    assert len(first_harness.resolver_calls) == 1

    second, second_harness = _scenario("retry", resolver_failure=True)
    terminal = materialize_living_dex_causal_example(
        second,
        store=store,
        claim_registry=registry,
    )
    assert not terminal.retry_allowed
    assert terminal.disposition is LivingDexCausalDisposition.RECOVERED_PREINPUT_FAILED
    assert second_harness.resolver_calls == [first_harness.resolver_calls[0]]


def test_controller_release_crash_is_target_free_and_never_reexecutes(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario("release-crash")

    def interrupt(stage: str) -> None:
        if stage == "after_controller_release":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        materialize_living_dex_causal_example(
            scenario,
            store=store,
            claim_registry=registry,
            failpoint=interrupt,
        )
    assert harness.executions == []

    recovered = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )
    assert recovered.disposition is LivingDexCausalDisposition.RECOVERED_INTERRUPTED
    assert recovered.example is None
    assert len(harness.resolver_calls) == 1
    assert harness.executions == []


def test_changed_effect_meter_forbids_preinput_recovery(tmp_path: Path) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario("changed-meter")

    def interrupt(stage: str) -> None:
        if stage == "after_construction_ready":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        materialize_living_dex_causal_example(
            scenario,
            store=store,
            claim_registry=registry,
            failpoint=interrupt,
        )
    harness.meter.emulator_frames += 1
    receipt = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )
    assert receipt.disposition is LivingDexCausalDisposition.RECOVERED_PREINPUT_FAILED
    assert receipt.terminal is not None
    assert receipt.terminal.reason_code == "protected_effect_changed_before_recovery"
    assert harness.executions == []


def test_new_meter_incarnation_after_power_loss_cannot_resume_construction(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario("new-meter-instance")

    def interrupt(stage: str) -> None:
        if stage == "after_construction_ready":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        materialize_living_dex_causal_example(
            scenario,
            store=store,
            claim_registry=registry,
            failpoint=interrupt,
        )
    restarted_meter = _Meter(
        scenario.effect_meter.binding_sha256,
        _sha("different-process-instance"),
    )
    recovered = materialize_living_dex_causal_example(
        replace(scenario, effect_meter=restarted_meter),
        store=store,
        claim_registry=registry,
    )
    assert recovered.disposition is LivingDexCausalDisposition.RECOVERED_PREINPUT_FAILED
    assert recovered.terminal is not None
    assert recovered.terminal.reason_code == "effect_meter_instance_changed_before_recovery"
    assert len(harness.resolver_calls) == 1
    assert harness.executions == []


@pytest.mark.parametrize(
    ("stage", "expected_executions", "expected_example"),
    (
        ("after_store_anchor", 1, True),
        ("after_pair_claim", 1, True),
        ("after_local_claim", 1, True),
        ("after_behavior_commitment", 1, True),
        ("after_behavior_selection", 1, True),
        ("after_construction_start", 1, True),
        ("after_construction_ready", 1, True),
        ("after_execution_start", 1, True),
        ("after_controller_release", 0, False),
        ("after_example_publish", 1, True),
        ("after_terminal_publish", 1, True),
    ),
)
def test_every_durable_cutpoint_recovers_without_duplicate_input(
    tmp_path: Path,
    stage: str,
    expected_executions: int,
    expected_example: bool,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario(f"crash-{stage}")
    tripped = False

    def interrupt(name: str) -> None:
        nonlocal tripped
        if name == stage and not tripped:
            tripped = True
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        materialize_living_dex_causal_example(
            scenario,
            store=store,
            claim_registry=registry,
            failpoint=interrupt,
        )
    recovered = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )
    assert len(harness.executions) == expected_executions
    assert (recovered.example is not None) is expected_example
    assert len(harness.observations) == expected_executions
    assert len(harness.resolver_calls) <= 2


def test_controller_gate_stays_locked_during_selected_arm_construction(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario("locked-gate")

    @contextmanager
    def eager_resolver(
        _index: int,
        gate: LivingDexControllerGate,
    ) -> Iterator[LivingDexCausalResolvedArm]:
        gate.require_released()
        raise AssertionError("locked gate unexpectedly allowed eager execution")
        yield  # pragma: no cover

    receipt = materialize_living_dex_causal_example(
        replace(scenario, resolve_selected=eager_resolver),
        store=store,
        claim_registry=registry,
    )
    assert receipt.disposition is LivingDexCausalDisposition.RECOVERED_PREINPUT_FAILED
    assert not receipt.retry_allowed
    assert harness.executions == []


def test_executor_exception_is_observed_instead_of_becoming_counterfactual_label(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario("executor-exception")

    @contextmanager
    def failing_resolver(
        index: int,
        gate: LivingDexControllerGate,
    ) -> Iterator[LivingDexCausalResolvedArm]:
        harness.resolver_calls.append(index)

        def execute(controller_gate: LivingDexControllerGate) -> None:
            controller_gate.require_released()
            harness.executions.append(index)
            harness.meter.controller_actions += 1
            harness.meter.emulator_frames += 4
            raise RuntimeError("ordinary selected-arm failure")

        yield LivingDexCausalResolvedArm(
            scenario.binding_sha256s[index],
            harness.meter,
            execute,
            lambda: {"actions": ["a"], "selected": index},
        )

    receipt = materialize_living_dex_causal_example(
        replace(scenario, resolve_selected=failing_resolver),
        store=store,
        claim_registry=registry,
    )
    assert receipt.example is not None
    assert receipt.example.outcome.status is LivingDexOutcomeStatus.SETTLED
    assert len(harness.observations) == 1
    assert len(harness.executions) == 1


def test_process_interruption_after_input_is_permanently_target_free(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario("input-interruption")

    @contextmanager
    def interrupting_resolver(
        index: int,
        gate: LivingDexControllerGate,
    ) -> Iterator[LivingDexCausalResolvedArm]:
        harness.resolver_calls.append(index)

        def execute(controller_gate: LivingDexControllerGate) -> None:
            controller_gate.require_released()
            harness.executions.append(index)
            harness.meter.controller_actions += 1
            harness.meter.emulator_frames += 1
            raise KeyboardInterrupt

        yield LivingDexCausalResolvedArm(
            scenario.binding_sha256s[index],
            harness.meter,
            execute,
            lambda: {"actions": ["a"]},
        )

    interrupted = replace(scenario, resolve_selected=interrupting_resolver)
    with pytest.raises(KeyboardInterrupt):
        materialize_living_dex_causal_example(
            interrupted,
            store=store,
            claim_registry=registry,
        )
    recovered = materialize_living_dex_causal_example(
        interrupted,
        store=store,
        claim_registry=registry,
    )
    assert recovered.disposition is LivingDexCausalDisposition.RECOVERED_INTERRUPTED
    assert recovered.example is None
    assert len(harness.executions) == 1
    assert len(harness.observations) == 0


def test_observer_controller_side_effect_can_never_be_a_train_target(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario("observer-side-effect")

    def unsafe_observer() -> LivingDexCausalObservation:
        harness.meter.controller_actions += 1
        return scenario.observe_after()

    receipt = materialize_living_dex_causal_example(
        replace(scenario, observe_after=unsafe_observer),
        store=store,
        claim_registry=registry,
    )
    assert receipt.example is not None
    assert receipt.example.outcome.status is LivingDexOutcomeStatus.CENSORED
    assert receipt.public_dict()["causal_train_example_recorded"] is False


@pytest.mark.parametrize("title_shape", ("red-shaped", "crystal-shaped"))
def test_title_shapes_share_one_policy_and_journal_contract(
    tmp_path: Path,
    title_shape: str,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, _harness = _scenario(title_shape, title_shape=title_shape)
    receipt = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=registry,
    )
    assert receipt.public_dict()["schema"] == "pokemon.core.living-dex-causal-receipt.v1"
    assert receipt.example is not None
    encoded = receipt.example.public_dict()
    assert title_shape not in str(encoded).lower()
    assert "private." not in str(encoded).lower()


def test_cross_lineage_relabelling_cannot_reclaim_identical_state(
    tmp_path: Path,
) -> None:
    shared_state = _sha("shared-state")
    shared_envelope = _sha("shared-envelope")
    store, registry = _store_and_registry(tmp_path)
    red, _ = _scenario("red-lineage", state=shared_state, envelope=shared_envelope)
    materialize_living_dex_causal_example(red, store=store, claim_registry=registry)

    other_store, _ = _store_and_registry(tmp_path / "other")
    crystal, _ = _scenario(
        "crystal-lineage",
        state=shared_state,
        envelope=shared_envelope,
        lineage=_sha("new-lineage"),
    )
    with pytest.raises(LivingDexCausalJournalError, match="already consumed"):
        materialize_living_dex_causal_example(
            crystal,
            store=other_store,
            claim_registry=registry,
        )


def test_global_claim_can_resume_only_in_its_original_private_store(
    tmp_path: Path,
) -> None:
    original_store, registry = _store_and_registry(tmp_path / "original")
    other_store, _other_registry = _store_and_registry(tmp_path / "other")
    scenario, harness = _scenario("store-bound")

    def interrupt(stage: str) -> None:
        if stage == "after_pair_claim":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        materialize_living_dex_causal_example(
            scenario,
            store=original_store,
            claim_registry=registry,
            failpoint=interrupt,
        )
    with pytest.raises(LivingDexCausalJournalError, match="already consumed"):
        materialize_living_dex_causal_example(
            scenario,
            store=other_store,
            claim_registry=registry,
        )
    recovered = materialize_living_dex_causal_example(
        scenario,
        store=original_store,
        claim_registry=registry,
    )
    assert recovered.example is not None
    assert len(harness.executions) == 1


def test_same_lineage_cannot_reclaim_different_state(tmp_path: Path) -> None:
    shared_lineage = _sha("shared-lineage")
    store, registry = _store_and_registry(tmp_path)
    first, _ = _scenario("first", lineage=shared_lineage)
    materialize_living_dex_causal_example(first, store=store, claim_registry=registry)

    other_store, _ = _store_and_registry(tmp_path / "other")
    second, _ = _scenario("second", lineage=shared_lineage)
    second = replace(
        second,
        identity=replace(
            second.identity,
            setup_terminal_sha256=first.identity.setup_terminal_sha256,
            setup_pair_claim_sha256=first.identity.setup_pair_claim_sha256,
            setup_attestation_sha256=first.identity.setup_attestation_sha256,
            menu_sha256=first.identity.menu_sha256,
        ),
    )
    with pytest.raises(LivingDexCausalJournalError, match="already consumed"):
        materialize_living_dex_causal_example(
            second,
            store=other_store,
            claim_registry=registry,
        )
