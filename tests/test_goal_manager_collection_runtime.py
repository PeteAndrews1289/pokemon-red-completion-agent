from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.captured_progress import write_captured_progress
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.goal_manager import (
    GoalFailureReason,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_collection_runtime import (
    GoalManagerCollectionRuntimeError,
    preflight_goal_manager_context,
    record_goal_manager_context,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogEntry,
    build_goal_manager_context_catalog_payload,
    goal_manager_catalog_episode_metadata,
    open_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
    parse_goal_manager_registry,
)
from pokemon_red_completion.goal_manager_runtime import (
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.observation import (
    InputReadiness,
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)
from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalOpportunityEnumerator,
)
from pokemon_red_completion.red_goal_skills import (
    RedGoalSkillAvailability,
    RedObservedGoalSkillProvider,
)
from pokemon_red_completion.trajectory import SemanticSnapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _Reader:
    def read(self) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=1,
            player_x=2,
            player_y=3,
            party_count=1,
            battle_state=0,
            party_species_ids=(0x1C,),
            party_levels=(60,),
            party_hp=(180,),
            party_max_hp=(180,),
            party_status=(0,),
            party_moves=((57, 58, 55, 0),),
            party_pp=((15, 10, 5, 0),),
        )

    def read_pokedex_state(self) -> RedPokedexState:
        return RedPokedexState(frozenset({9}), frozenset({9}))

    def read_all_box_states(self) -> RedBoxCollectionState:
        return RedBoxCollectionState(
            tuple(RedCurrentBoxState(index, (), ()) for index in range(12)),
            0,
            False,
        )

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0, 0, 0, 0, 0)


class _Observer:
    def __init__(self) -> None:
        self.facts: frozenset[str] = frozenset()

    def observe_raw(self, _raw: RawGameState) -> GameState:
        return GameState(GameMode.OVERWORLD, self.facts, "test")

    def observe(self) -> GameState:
        return GameState(GameMode.OVERWORLD, self.facts, "test")


class _World:
    def __init__(self, observer: _Observer) -> None:
        self.observer = observer

    def execute(self, action: MacroAction) -> MacroAction:
        self.observer.facts = frozenset({"story:first"})
        return action


class _SnapshotProvider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id="pokemon.mainline:red:gb:us:rev0",
            mode="overworld",
            location="pokemon.red:area:test",
            features={},
        )


def _registry():  # type: ignore[no-untyped-def]
    registry = parse_goal_manager_registry(
        (PROJECT_ROOT / GOAL_MANAGER_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    registry = replace(
        registry,
        execution=replace(registry.execution, source_commit="a" * 40),
    )
    return registry


def _assignment():  # type: ignore[no-untyped-def]
    return _registry().assignment("red-goal-v1-001-advance_story-train-01")


def _catalog(registry, focused_preflight):  # type: ignore[no-untyped-def]
    entries = []
    for ordinal, slot in enumerate(registry.slots, start=1):
        assignment = registry.assignment(slot.slot_id)
        if assignment.assignment_id == focused_preflight.assignment_id:
            question_sha256 = focused_preflight.question_sha256
            binding_manifest_sha256 = focused_preflight.binding_manifest_sha256
            capture_id = focused_preflight.capture_id
            state_sha256 = focused_preflight.state_sha256
            envelope_sha256 = focused_preflight.envelope_sha256
            focus_pressure = focused_preflight.focus_pressure
            available = focused_preflight.available_goal_kinds
        else:
            question_sha256 = hashlib.sha256(
                f"question-{ordinal}".encode("ascii")
            ).hexdigest()
            binding_manifest_sha256 = hashlib.sha256(
                f"bindings-{ordinal}".encode("ascii")
            ).hexdigest()
            capture_id = f"capture-{ordinal:03d}"
            state_sha256 = hashlib.sha256(
                f"state-{ordinal}".encode("ascii")
            ).hexdigest()
            envelope_sha256 = hashlib.sha256(
                f"envelope-{ordinal}".encode("ascii")
            ).hexdigest()
            focus_pressure = 0.5 + ordinal / 1_000
            kinds = {slot.focus_kind}
            for kind in GoalKind:
                kinds.add(kind)
                if len(kinds) == 3:
                    break
            available = tuple(kinds)
        entries.append(
            GoalManagerContextCatalogEntry.build(
                assignment=assignment,
                capture_id=capture_id,
                state_sha256=state_sha256,
                envelope_sha256=envelope_sha256,
                question_sha256=question_sha256,
                binding_manifest_sha256=binding_manifest_sha256,
                focus_pressure=focus_pressure,
                selected_kind=slot.focus_kind,
                available_goal_kinds=available,
            )
        )
    payload = build_goal_manager_context_catalog_payload(registry, tuple(entries))
    return parse_goal_manager_context_catalog(payload, registry)


def _adapter(observer: _Observer) -> PokemonRedGoalStateAdapter:
    graph = QuestGraph(
        (
            Objective(
                "first",
                "First",
                frozenset({"story:first"}),
                Specialist.INTERACTION,
            ),
        )
    )
    return PokemonRedGoalStateAdapter(_Reader(), observer, graph)


def _factory(adapter: PokemonRedGoalStateAdapter):  # type: ignore[no-untyped-def]
    def build(actions):  # type: ignore[no-untyped-def]
        def provider(kind: GoalKind, effort: float, risk: float):
            def execute() -> GoalExecutionReport:
                before = actions.actions_executed
                actions.execute(MacroAction(MacroActionKind.WAIT))
                return GoalExecutionReport(
                    actions.actions_executed - before,
                    1,
                    {"bounded": True},
                )

            def verify(before, after, _report):  # type: ignore[no-untyped-def]
                if before.game_state.facts.issubset(after.game_state.facts) and (
                    "story:first" in after.game_state.facts
                ):
                    return GoalVerification.succeeded()
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

            return RedObservedGoalSkillProvider(
                kind=kind,
                binding_ref=f"pokemon.red:test:{kind.value}",
                adapter=adapter,
                availability=lambda _observation: RedGoalSkillAvailability.available(),
                executor=execute,
                verifier=verify,
                estimated_effort=effort,
                estimated_risk=risk,
            )

        return RedGoalOpportunityEnumerator(
            (
                provider(GoalKind.ADVANCE_STORY, 0.01, 0.01),
                provider(GoalKind.ACQUIRE_SPECIES, 1.0, 1.0),
                provider(GoalKind.EXPLORE, 1.0, 1.0),
            )
        )

    return build


def _private_store(tmp_path: Path):  # type: ignore[no-untyped-def]
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    return initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )


def _capture(tmp_path: Path):  # type: ignore[no-untyped-def]
    state_path = tmp_path / "context.state"
    envelope_path = tmp_path / "context.state.json"
    state_path.write_bytes(b"authenticated-context-state")
    write_captured_progress(
        envelope_path,
        state_path=state_path,
        checkpoint_id="goal-context-capture",
        checkpoint_label="Goal context capture",
        checkpoints_completed=1,
        checkpoints_total=1,
        verified_objective_ids=(),
    )
    return open_goal_manager_context_capture(state_path, envelope_path)


def test_goal_context_preflight_and_recording_form_one_strict_episode(
    tmp_path: Path,
) -> None:
    observer = _Observer()
    adapter = _adapter(observer)
    registry = _registry()
    assignment = registry.assignment("red-goal-v1-001-advance_story-train-01")
    world = _World(observer)
    factory = _factory(adapter)
    capture = _capture(tmp_path)

    preflight = preflight_goal_manager_context(
        assignment=assignment,
        capture=capture,
        adapter=adapter,
        enumerator=factory(type("Actions", (), {"actions_executed": 0})()),
    )

    assert preflight.passed
    assert preflight.selected_kind is GoalKind.ADVANCE_STORY
    assert preflight.available_goal_count == 3
    catalog = _catalog(registry, preflight)

    result = record_goal_manager_context(
        private_root=_private_store(tmp_path),
        assignment=assignment,
        capture=capture,
        context_catalog=catalog,
        metadata=goal_manager_catalog_episode_metadata(assignment, catalog),
        adapter=adapter,
        snapshot_provider=_SnapshotProvider(),
        action_delegate=world,
        enumerator_factory=factory,
    )

    assert result.execution.passed
    assert result.dataset.examples[0].teacher_choice_target is not None
    assert result.dataset.examples[0].selected_kind is GoalKind.ADVANCE_STORY
    assert result.episode_summary["status"] == "complete"
    assert result.public_dict()["private_path_fields"] == 0


def test_preflight_accepts_an_honest_singleton_emergency_context(
    tmp_path: Path,
) -> None:
    observer = _Observer()
    adapter = _adapter(observer)
    assignment = _assignment()
    available = RedObservedGoalSkillProvider(
        kind=GoalKind.ADVANCE_STORY,
        binding_ref="pokemon.red:test:story",
        adapter=adapter,
        availability=lambda _observation: RedGoalSkillAvailability.available(),
        executor=lambda: GoalExecutionReport(0, 0, {}),
        verifier=lambda _before, _after, _report: GoalVerification.succeeded(),
        estimated_effort=0.1,
        estimated_risk=0.1,
    )

    preflight = preflight_goal_manager_context(
        assignment=assignment,
        capture=_capture(tmp_path),
        adapter=adapter,
        enumerator=RedGoalOpportunityEnumerator((available,)),
    )

    assert preflight.passed
    assert preflight.available_goal_count == 1
    assert preflight.available_goal_kinds == (GoalKind.ADVANCE_STORY,)


def test_preflight_reports_zero_executable_goals_before_question_construction(
    tmp_path: Path,
) -> None:
    observer = _Observer()
    adapter = _adapter(observer)
    unavailable = RedObservedGoalSkillProvider(
        kind=GoalKind.ADVANCE_STORY,
        binding_ref="pokemon.red:test:masked-story",
        adapter=adapter,
        availability=lambda _observation: RedGoalSkillAvailability.unavailable(
            GoalUnavailableReason.NO_LEGAL_TARGET
        ),
        executor=lambda: GoalExecutionReport(0, 0, {}),
        verifier=lambda _before, _after, _report: GoalVerification.succeeded(),
        estimated_effort=0.1,
        estimated_risk=0.1,
    )

    with pytest.raises(
        GoalManagerCollectionRuntimeError,
        match="no_available_goal",
    ):
        preflight_goal_manager_context(
            assignment=_assignment(),
            capture=_capture(tmp_path),
            adapter=adapter,
            enumerator=RedGoalOpportunityEnumerator((unavailable,)),
        )
