from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/run_repeatable_goal_manager_development.py"),
    run_name="repeatable_goal_manager_development_script_test",
)


def _campaign() -> dict[str, object]:
    campaign_id = "a" * 64
    focus_kinds = ("develop_team", "restore_team", "manage_storage", "acquire_species")
    roots = []
    for index, focus_kind in enumerate(focus_kinds):
        digest = f"{index + 1:x}" * 64
        available_goal_kinds = [focus_kind, "explore"]
        if focus_kind == GoalKind.DEVELOP_TEAM.value:
            available_goal_kinds = [focus_kind, GoalKind.ADVANCE_STORY.value]
        roots.append(
            {
                "assignment_id": digest,
                "available_goal_kinds": available_goal_kinds,
                "available_menu_sha256": digest,
                "binding_manifest_sha256": digest,
                "capture_id": f"red-goal-v1-{index + 1:02d}-train",
                "entry_index": index,
                "envelope_file_sha256": digest,
                "envelope_sha256": digest,
                "focus_kind": focus_kind,
                "policy_context_sha256": digest,
                "profile_file_sha256": digest,
                "question_sha256": digest,
                "root_lineage_id": f"red-goal-root-{digest}",
                "state_file_sha256": digest,
                "state_sha256": digest,
            }
        )
    trials = []
    for trial_index in range(12):
        trials.append(
            {
                "episode_id": f"red-goal-dev-{campaign_id}-{trial_index:02d}",
                "maximum_decisions": 3,
                "root_index": trial_index // 3,
                "seed": 10_000 + (trial_index // 3) * 100 + trial_index % 3,
                "trial_claim_sha256": canonical_sha256(
                    {
                        "campaign_id": campaign_id,
                        "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
                        "trial_index": trial_index,
                    }
                ),
                "trial_index": trial_index,
            }
        )
    return {"campaign_id": campaign_id, "roots": roots, "trials": trials}


def test_parser_separates_freeze_preflight_and_execution() -> None:
    parser = SCRIPT["_parser"]()
    options = {option for action in parser._actions for option in action.option_strings}
    assert {"--mode", "--campaign-plan", "--expected-campaign-sha256"} <= options
    assert {"--private-root", "--trial-index"} <= options
    assert {
        "--expected-source-commit",
        "--expected-source-bundle-sha256",
        "--expected-runner-sha256",
        "--expected-runtime-sha256",
        "--expected-numpy-runtime-sha256",
        "--expected-skill-manifest-sha256",
        "--expected-context-plan-sha256",
    } <= options


def test_campaign_layout_freezes_four_roots_and_twelve_exact_trials() -> None:
    SCRIPT["_validate_campaign_layout"](_campaign())


def test_campaign_focuses_have_real_choice_signal_and_keep_story_as_a_candidate() -> None:
    assert tuple(SCRIPT["REQUIRED_FOCUS_KINDS"]) == (
        GoalKind.DEVELOP_TEAM,
        GoalKind.RESTORE_TEAM,
        GoalKind.MANAGE_STORAGE,
        GoalKind.ACQUIRE_SPECIES,
    )

    develop_root = _campaign()["roots"][0]
    assert develop_root["focus_kind"] == GoalKind.DEVELOP_TEAM.value
    assert GoalKind.ADVANCE_STORY.value in develop_root["available_goal_kinds"]


def test_freeze_produced_real_identifier_shapes_round_trip_through_campaign_loader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_globals = SCRIPT["_freeze"].__globals__
    focuses = tuple(SCRIPT["REQUIRED_FOCUS_KINDS"])
    entries = tuple(
        SimpleNamespace(slot_id=f"red-goal-v1-{index + 1:02d}-train")
        for index in range(4)
    )
    assignments = {}
    roots = []
    for index, (entry, focus) in enumerate(zip(entries, focuses, strict=True)):
        digest = f"{index + 1:x}" * 64
        assignment = SimpleNamespace(
            assignment_id=digest,
            root_lineage_id=f"red-goal-root-{digest}",
            focus_kind=focus,
            partition="train",
        )
        assignments[entry.slot_id] = assignment
        roots.append(
            SimpleNamespace(
                assignment=assignment,
                capture=SimpleNamespace(
                    capture_id=entry.slot_id,
                    state_sha256=digest,
                    envelope_sha256=digest,
                ),
                entry_index=index,
                state_file_sha256=digest,
                envelope_file_sha256=digest,
                profile_file_sha256=digest,
                question_sha256=digest,
                policy_context_sha256=digest,
                available_menu_sha256=digest,
                binding_manifest_sha256=digest,
                available_goal_kinds=(focus.value, GoalKind.EXPLORE.value),
            )
        )

    class Registry:
        registry_sha256 = "7" * 64

        def assignment(self, slot_id: str) -> object:
            return assignments[slot_id]

    candidate = SimpleNamespace(
        catalog=SimpleNamespace(catalog_sha256="8" * 64),
        fit_summary_sha256="9" * 64,
        plan=SimpleNamespace(
            model_canonical_sha256="a" * 64,
            model_file_sha256="b" * 64,
            plan_sha256="c" * 64,
        ),
        registry=Registry(),
    )
    rom_dir = tmp_path / "rom"
    plan_dir = tmp_path / "plans"
    rom_dir.mkdir()
    plan_dir.mkdir()
    readiness = SimpleNamespace(
        rom_path=rom_dir / "red.gb",
        rom=SimpleNamespace(sha256="d" * 64),
        entries=entries,
        candidate=candidate,
        context_plan_sha256="e" * 64,
        numpy_runtime_sha256="f" * 64,
        runtime=SimpleNamespace(sha256="1" * 64),
        runner_sha256="2" * 64,
        skill_manifest_sha256="3" * 64,
        source_bundle_sha256="4" * 64,
        source=SimpleNamespace(git_commit="5" * 40),
    )
    private_identity = "6" * 64
    registry_path = tmp_path / "registry"
    registry_path.mkdir()
    monkeypatch.setitem(
        runtime_globals,
        "_open_bound_private_root",
        lambda *_args, **_kwargs: (object(), private_identity),
    )
    monkeypatch.setitem(
        runtime_globals,
        "open_fixed_account_claim_registry",
        lambda: registry_path,
    )
    monkeypatch.setitem(
        runtime_globals,
        "_historical_root_is_open",
        lambda *_args: True,
    )
    monkeypatch.setitem(
        runtime_globals,
        "_inspect_root",
        lambda _readiness, _entry, *, entry_index: roots[entry_index],
    )
    monkeypatch.setitem(runtime_globals, "rom_adjacent_artifacts", lambda _path: ())
    destination = plan_dir / "campaign.json"

    receipt = SCRIPT["_freeze"](readiness, destination, tmp_path / "private")
    loaded_path, loaded_sha, loaded = SCRIPT["_load_campaign"](
        destination,
        readiness,
        expected_campaign_sha256=receipt["campaign_plan_sha256"],
        expected_private_root_identity_sha256=private_identity,
    )

    assert loaded_path == destination.resolve()
    assert loaded_sha == receipt["campaign_plan_sha256"]
    assert len(loaded["roots"]) == 4
    assert len(loaded["trials"]) == 12


def test_external_executable_mismatch_fails_before_rom_or_private_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_globals = SCRIPT["_readiness"].__globals__
    source = SimpleNamespace(git_commit="1" * 40)
    monkeypatch.setitem(runtime_globals, "_require_project_import_origins", lambda: None)
    monkeypatch.setitem(
        runtime_globals,
        "detect_source_identity",
        lambda *_args, **_kwargs: source,
    )
    monkeypatch.setitem(runtime_globals, "require_clean_source", lambda _source: None)
    monkeypatch.setitem(
        runtime_globals,
        "require_published_source",
        lambda *_args: None,
    )
    monkeypatch.setitem(runtime_globals, "_file_sha256", lambda _path: "2" * 64)
    monkeypatch.setitem(
        runtime_globals,
        "build_runtime_identity",
        lambda: SimpleNamespace(sha256="3" * 64),
    )
    monkeypatch.setitem(
        runtime_globals,
        "goal_manager_development_numpy_runtime_sha256",
        lambda: "4" * 64,
    )
    monkeypatch.setitem(
        runtime_globals,
        "working_source_bundle_sha256",
        lambda _root: "5" * 64,
    )
    monkeypatch.setitem(
        runtime_globals,
        "composition_skill_manifest",
        lambda _root: {"manifest_sha256": "6" * 64},
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external mismatch reached a protected input")

    monkeypatch.setitem(runtime_globals, "resolve_rom_path", forbidden)
    args = SimpleNamespace(
        expected_source_commit="0" * 40,
        expected_source_bundle_sha256="5" * 64,
        expected_runner_sha256="2" * 64,
        expected_runtime_sha256="3" * 64,
        expected_numpy_runtime_sha256="4" * 64,
        expected_skill_manifest_sha256="6" * 64,
    )
    with pytest.raises(
        SCRIPT["RepeatableGoalManagerRunError"],
        match="external_executable_attestation",
    ):
        SCRIPT["_readiness"](args)


def test_external_context_plan_mismatch_fails_before_plan_admission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_globals = SCRIPT["_readiness"].__globals__
    source = SimpleNamespace(git_commit="1" * 40)
    context_plan = tmp_path / "contexts.json"
    context_plan.write_text("{}\n")
    monkeypatch.setitem(runtime_globals, "_require_project_import_origins", lambda: None)
    monkeypatch.setitem(
        runtime_globals,
        "detect_source_identity",
        lambda *_args, **_kwargs: source,
    )
    monkeypatch.setitem(runtime_globals, "require_clean_source", lambda _source: None)
    monkeypatch.setitem(runtime_globals, "require_published_source", lambda *_args: None)
    monkeypatch.setitem(runtime_globals, "_file_sha256", lambda _path: "2" * 64)
    monkeypatch.setitem(
        runtime_globals,
        "build_runtime_identity",
        lambda: SimpleNamespace(sha256="3" * 64),
    )
    monkeypatch.setitem(
        runtime_globals,
        "goal_manager_development_numpy_runtime_sha256",
        lambda: "4" * 64,
    )
    monkeypatch.setitem(
        runtime_globals,
        "working_source_bundle_sha256",
        lambda _root: "5" * 64,
    )
    monkeypatch.setitem(
        runtime_globals,
        "composition_skill_manifest",
        lambda _root: {"manifest_sha256": "6" * 64},
    )
    monkeypatch.setitem(runtime_globals, "resolve_rom_path", lambda _path: tmp_path / "red.gb")
    monkeypatch.setitem(
        runtime_globals,
        "verify_rom",
        lambda _path: SimpleNamespace(sha256="7" * 64),
    )
    monkeypatch.setitem(
        runtime_globals,
        "load_committed_goal_manager_promotion_plan",
        lambda _root: (object(), "1" * 40),
    )
    monkeypatch.setitem(runtime_globals, "_external_regular", lambda path, **_kwargs: path)
    monkeypatch.setitem(
        runtime_globals,
        "authenticate_goal_manager_candidate",
        lambda **_kwargs: object(),
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("mismatched context plan reached admission")

    monkeypatch.setitem(runtime_globals, "_load_context_plan", forbidden)
    args = SimpleNamespace(
        expected_source_commit="1" * 40,
        expected_source_bundle_sha256="5" * 64,
        expected_runner_sha256="2" * 64,
        expected_runtime_sha256="3" * 64,
        expected_numpy_runtime_sha256="4" * 64,
        expected_skill_manifest_sha256="6" * 64,
        expected_context_plan_sha256="0" * 64,
        rom=tmp_path / "red.gb",
        context_catalog=tmp_path / "catalog.json",
        model=tmp_path / "model.json",
        fit_summary=tmp_path / "fit.json",
        context_plan=context_plan,
    )
    with pytest.raises(
        SCRIPT["RepeatableGoalManagerRunError"],
        match="external_context_plan_attestation",
    ):
        SCRIPT["_readiness"](args)


@pytest.mark.parametrize(
    "mutation",
    ("duplicate_root", "missing_trial", "changed_claim", "changed_focus", "duplicate_seed"),
)
def test_campaign_layout_rejects_retry_or_semantic_drift(mutation: str) -> None:
    campaign = _campaign()
    roots = campaign["roots"]
    trials = campaign["trials"]
    assert isinstance(roots, list) and isinstance(trials, list)
    if mutation == "duplicate_root":
        roots[1]["root_lineage_id"] = roots[0]["root_lineage_id"]
    elif mutation == "missing_trial":
        trials.pop()
    elif mutation == "changed_claim":
        trials[0]["trial_claim_sha256"] = "f" * 64
    elif mutation == "changed_focus":
        roots[0]["focus_kind"] = "restore_team"
    else:
        trials[1]["seed"] = trials[0]["seed"]

    with pytest.raises(SCRIPT["RepeatableGoalManagerRunError"]):
        SCRIPT["_validate_campaign_layout"](campaign)


def test_deferred_executor_refuses_input_until_enumeration_finishes() -> None:
    calls: list[object] = []

    class Delegate:
        def execute(self, action: object) -> object:
            calls.append(action)
            return action

    gated = SCRIPT["_DeferredActionExecutor"](Delegate())
    with pytest.raises(
        SCRIPT["RepeatableGoalManagerRunError"],
        match="action_free_reobservation",
    ):
        gated.execute("forbidden")
    assert not calls
    gated.enable()
    assert gated.execute("allowed") == "allowed"
    assert calls == ["allowed"]


def test_live_observer_passes_a_real_counting_executor_to_context_enumerator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    available = {GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM}
    opportunities = tuple(
        GoalOpportunity(
            binding_ref=f"test:{kind.value}",
            kind=kind,
            availability=(
                GoalAvailability.AVAILABLE
                if kind in available
                else GoalAvailability.UNAVAILABLE
            ),
            estimated_effort=0.2 if kind in available else None,
            estimated_risk=0.1 if kind in available else None,
            unavailable_reason=(
                None if kind in available else GoalUnavailableReason.NO_LEGAL_TARGET
            ),
        )
        for kind in GoalKind
    )
    bindings = tuple(
        ExecutableGoalBinding(
            binding_ref=f"test:{kind.value}",
            kind=kind,
            estimated_effort=0.2,
            estimated_risk=0.1,
            execute=lambda: GoalExecutionReport(0, 0, {}),
            verify=lambda _report: GoalVerification.succeeded(),
        )
        for kind in sorted(available, key=lambda item: item.value)
    )
    binding_set = GoalBindingSet(opportunities, bindings)
    situation = GoalSituation(*([0.5] * 9))

    class Live:
        def __init__(self) -> None:
            self.situation = situation

        def public_dict(self) -> dict[str, object]:
            return {"schema": "test-live-observation.v1"}

    class Adapter:
        def observe(self) -> Live:
            return Live()

    class Enumerator:
        def enumerate(self, _live: Live) -> GoalBindingSet:
            return binding_set

    class Runtime:
        adapter = Adapter()

        def enumerator(self, actions: CountingExecutor) -> Enumerator:
            fake_runtime = SimpleNamespace(
                profile=SimpleNamespace(providers=(), profile_sha256="a" * 64)
            )
            RedGoalContextRuntime.enumerator(fake_runtime, actions)
            return Enumerator()

    class Delegate:
        def execute(self, action: object) -> object:
            return action

    class Meter:
        def checkpoint(self) -> CompositionBudgetCheckpoint:
            return CompositionBudgetCheckpoint(0, 0)

        def begin_decision_window(self) -> None:
            return None

    checkpoint = LivingCollectionCheckpoint(
        registered_species=1,
        living_species=1,
        required_specimens_remaining=1,
        retained_captures=1,
        storage_headroom=1,
        undeclared_specimen_losses=0,
        completion_contract_sha256="1" * 64,
        specimen_ledger_sha256="2" * 64,
        required_specimens_sha256="3" * 64,
        specimen_counts=(("pokemon:national:001", 1),),
    )
    monkeypatch.setitem(
        SCRIPT["_live_observer"].__globals__,
        "living_collection_checkpoint",
        lambda _live: checkpoint,
    )
    assignment_id = "b" * 64
    current_assignment_id = "c" * 64
    question = SCRIPT["ordered_goal_manager_question"](
        assignment_id=assignment_id,
        decision_index=0,
        situation=situation,
        opportunities=opportunities,
    )
    root = SimpleNamespace(
        assignment=SimpleNamespace(assignment_id=current_assignment_id),
        question_sha256=question.ordered_policy_input_sha256,
        binding_manifest_sha256=SCRIPT["goal_binding_manifest_sha256"](binding_set),
    )
    observe = SCRIPT["_live_observer"](
        runtime=Runtime(),
        actions=CountingExecutor(Delegate()),
        meter=Meter(),
        root=root,
        ordering_assignment_id=assignment_id,
    )

    result = observe()
    assert result.binding_set == binding_set


def test_preflight_rejects_a_closed_historical_root_before_context_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    campaign = _campaign()
    runtime_globals = SCRIPT["_preflight"].__globals__
    campaign_path = tmp_path / "campaign.json"
    campaign_path.write_text("{}\n")
    private_root = tmp_path / "private"
    registry = tmp_path / "registry"
    registry.mkdir(mode=0o700)
    readiness = SimpleNamespace(
        entries=(object(), object(), object(), object()),
        rom_path=tmp_path / "red.gb",
    )
    monkeypatch.setitem(
        runtime_globals,
        "_load_campaign",
        lambda *_args, **_kwargs: (campaign_path, "a" * 64, campaign),
    )
    monkeypatch.setitem(
        runtime_globals,
        "_open_bound_private_root",
        lambda *_args, **_kwargs: (object(), "f" * 64),
    )
    monkeypatch.setitem(
        runtime_globals,
        "open_fixed_account_claim_registry",
        lambda: registry,
    )
    monkeypatch.setitem(
        runtime_globals,
        "_historical_root_is_open",
        lambda *_args: False,
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("closed root reached a context or episode open")

    monkeypatch.setitem(runtime_globals, "_open_frozen_root", forbidden)
    monkeypatch.setitem(runtime_globals, "open_private_root", forbidden)

    with pytest.raises(
        SCRIPT["RepeatableGoalManagerRunError"],
        match="closed_root_collision",
    ):
        SCRIPT["_preflight"](
            readiness,
            campaign_path,
            private_root,
            expected_campaign_sha256="a" * 64,
        )


def test_fixed_account_trial_claim_is_exclusive_and_path_free(tmp_path: Path) -> None:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    claim = "a" * 64
    SCRIPT["_write_trial_claim"](
        registry,
        trial_claim_sha256=claim,
        execution_identity_sha256="b" * 64,
        source_commit="c" * 40,
        runner_sha256="d" * 64,
    )
    assert not SCRIPT["_trial_claim_is_available"](registry, claim)
    marker = next(registry.iterdir())
    payload = json.loads(marker.read_text())
    assert payload["schema"] == "pokemon.red.repeatable-goal-manager-trial-claim.v1"
    assert str(tmp_path) not in marker.read_text()
    assert marker.stat().st_nlink == 1
    assert SCRIPT["_read_trial_claim"](registry, claim) == payload
    with pytest.raises(
        SCRIPT["RepeatableGoalManagerRunError"],
        match="trial_already_consumed",
    ):
        SCRIPT["_write_trial_claim"](
            registry,
            trial_claim_sha256=claim,
            execution_identity_sha256="b" * 64,
            source_commit="c" * 40,
            runner_sha256="d" * 64,
        )


def test_private_store_binding_changes_with_the_exact_opened_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_globals = SCRIPT["_open_bound_private_root"].__globals__
    first = tmp_path / "first" / "private"
    second = tmp_path / "second" / "private"
    rom = tmp_path / "rom" / "red.gb"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    rom.parent.mkdir()
    rom.write_bytes(b"rom")
    for root in (first, second):
        (root / SCRIPT["PRIVATE_ROOT_SENTINEL"]).write_bytes(b"sentinel")
    monkeypatch.setitem(runtime_globals, "open_private_root", lambda *_args, **_kwargs: object())
    monkeypatch.setitem(runtime_globals, "_file_sha256", lambda _path: "f" * 64)

    _first_store, first_identity = SCRIPT["_open_bound_private_root"](
        first,
        rom_path=rom,
    )
    _second_store, second_identity = SCRIPT["_open_bound_private_root"](
        second,
        rom_path=rom,
    )
    assert first_identity != second_identity


def test_trial_claim_write_failure_never_publishes_partial_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    os_module = SCRIPT["os"]

    def fail_write(_descriptor: int, _payload: bytes) -> int:
        raise OSError("injected write failure")

    monkeypatch.setattr(os_module, "write", fail_write)
    with pytest.raises(
        SCRIPT["RepeatableGoalManagerRunError"],
        match="trial_claim_registry",
    ):
        SCRIPT["_write_trial_claim"](
            registry,
            trial_claim_sha256="a" * 64,
            execution_identity_sha256="b" * 64,
            source_commit="c" * 40,
            runner_sha256="d" * 64,
        )
    assert list(registry.iterdir()) == []


def test_trial_claim_directory_fsync_failure_retains_complete_consumption(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    os_module = SCRIPT["os"]
    original_fsync = os_module.fsync
    calls = 0

    def fail_second_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os_module, "fsync", fail_second_fsync)
    claim = "a" * 64
    with pytest.raises(
        SCRIPT["RepeatableGoalManagerRunError"],
        match="trial_claim_registry",
    ):
        SCRIPT["_write_trial_claim"](
            registry,
            trial_claim_sha256=claim,
            execution_identity_sha256="b" * 64,
            source_commit="c" * 40,
            runner_sha256="d" * 64,
        )
    marker = registry / f"repeatable-development-{claim}.json"
    assert marker.stat().st_nlink == 1
    assert SCRIPT["_read_trial_claim"](registry, claim)[
        "execution_identity_sha256"
    ] == "b" * 64


def test_failure_envelope_never_claims_protected_access() -> None:
    receipt = SCRIPT["_failure_receipt"]("readiness_authentication")
    assert receipt["sealed_red_accesses"] == "not_attested_on_failure"
    assert receipt["crystal_accesses"] == "not_attested_on_failure"
    assert receipt["teacher_queries"] == 0
    assert receipt["teacher_fallbacks"] == 0
