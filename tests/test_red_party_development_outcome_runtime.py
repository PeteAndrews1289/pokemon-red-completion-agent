from __future__ import annotations

import json
from dataclasses import replace

import pytest
from test_party_development_adapter import _snapshot

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.party_development_frozen_catalog import (
    PartyDevelopmentFrozenQuestion,
)
from pokemon_red_completion.party_development_outcome_campaign import (
    RED_PARTY_DEVELOPMENT_OUTCOME_DOSE,
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import red_internal_species_number
from pokemon_red_completion.red_party_development_outcome_runtime import (
    BoundedActionExecutor,
    FrameBudgetEmulator,
    RedPartyDevelopmentOutcomeRuntimeError,
    automatic_level_evolution_lineage,
    bind_red_party_development_outcome_trial,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind
from pokemon_red_completion.training_venue import TrainingVenue


def _red_mapping() -> dict[int, int]:
    mapping: dict[int, int] = {}
    for internal in range(1, 191):
        try:
            mapping[internal] = red_internal_species_number(internal)
        except ValueError:
            continue
    return mapping


def _training_venues(snapshot: object) -> tuple[TrainingVenue, ...]:
    areas = snapshot.areas  # type: ignore[attr-defined]
    return tuple(
        TrainingVenue(
            band=area,
            map_id=index + 1,
            walk_to_grass=lambda _actions, _reader, _emulator: 1,
            heal_and_return=lambda _actions, _reader, _emulator: None,
            is_in_center=lambda _raw: False,
            move_slot=lambda _raw: 1,
        )
        for index, area in enumerate(areas)
    )


def _question_and_assignment(
    *,
    kind: TrainingChoiceKind,
    candidate_index: int,
):
    snapshot = _snapshot(
        partition=(
            ScenarioPartition.TRAIN
            if kind is TrainingChoiceKind.TRAINEE
            else ScenarioPartition.DEVELOPMENT
        )
    )
    if kind is TrainingChoiceKind.TRAINEE:
        menu = snapshot.trainee_menu(snapshot.areas[0])
        venue_trainee = None
    else:
        venue_trainee = snapshot.party.members[1]
        menu = snapshot.venue_menu(venue_trainee)
    assert menu is not None
    binding = snapshot.freeze_binding(menu, scenario_id="party-outcome-runtime-001")
    question = PartyDevelopmentFrozenQuestion(
        capture_id="capture-001",
        capture_envelope_sha256="8" * 64,
        profile_id="capture-001",
        profile_file_sha256="7" * 64,
        binding=binding,
        candidate_set=menu.candidate_set,
    )
    candidate = menu.candidate_set.candidates[candidate_index]
    assignment = PartyDevelopmentOutcomeTrialAssignment.build(
        ordinal=1,
        scenario_id=question.scenario_id,
        root_lineage_id=binding.root_lineage_id,
        initial_state_sha256=binding.initial_state_sha256,
        partition=binding.partition,
        kind=binding.kind,
        goal=binding.goal,
        binding_sha256=binding.binding_sha256,
        candidate_index=candidate_index,
        candidate_sha256=canonical_sha256(candidate.public_dict()),
        candidate_feature_sha256=binding.candidate_feature_sha256[candidate_index],
    )
    return snapshot, menu, venue_trainee, question, assignment


def test_trainee_trial_binds_selected_member_shared_venue_and_level_lineage() -> None:
    snapshot, menu, venue_trainee, question, assignment = _question_and_assignment(
        kind=TrainingChoiceKind.TRAINEE,
        candidate_index=1,
    )
    mapping = _red_mapping()
    start_national = mapping[snapshot.party.members[1].species_id]
    descendant_internal = next(
        internal for internal, national in mapping.items() if national == 131
    )

    bound = bind_red_party_development_outcome_trial(
        question,
        menu,
        assignment,
        party=snapshot.party,
        venue_question_trainee=venue_trainee,
        training_venues=_training_venues(snapshot),
        evolutions={
            start_national: (
                Evolution(start_national, 131, EvolutionMethod.LEVEL, 31),
            )
        },
        internal_to_national=mapping,
        dose=RED_PARTY_DEVELOPMENT_OUTCOME_DOSE,
    )

    assert bound.target_slot == snapshot.party.members[1].slot
    assert bound.trainee_species_lineage == tuple(
        sorted((snapshot.party.members[1].species_id, descendant_internal))
    )
    assert bound.venue_identity == snapshot.areas[0].identity
    assert bound.fixed_dose.completed_battles == 4
    encoded = json.dumps(bound.public_summary(), sort_keys=True)
    assert snapshot.areas[0].area_id not in encoded
    assert "target_species" not in encoded
    assert "target_slot" not in encoded


def test_venue_trial_binds_fixed_trainee_and_selected_venue() -> None:
    snapshot, menu, venue_trainee, question, assignment = _question_and_assignment(
        kind=TrainingChoiceKind.VENUE,
        candidate_index=1,
    )
    assert venue_trainee is not None

    bound = bind_red_party_development_outcome_trial(
        question,
        menu,
        assignment,
        party=snapshot.party,
        venue_question_trainee=venue_trainee,
        training_venues=_training_venues(snapshot),
        evolutions={},
        internal_to_national=_red_mapping(),
        dose=RED_PARTY_DEVELOPMENT_OUTCOME_DOSE,
    )

    assert bound.target_slot == venue_trainee.slot
    assert bound.venue_identity == snapshot.areas[1].identity


def test_trial_binding_rejects_rehashed_assignment_from_another_candidate() -> None:
    snapshot, menu, venue_trainee, question, assignment = _question_and_assignment(
        kind=TrainingChoiceKind.TRAINEE,
        candidate_index=1,
    )
    wrong = PartyDevelopmentOutcomeTrialAssignment.build(
        ordinal=assignment.ordinal,
        scenario_id=assignment.scenario_id,
        root_lineage_id=assignment.root_lineage_id,
        initial_state_sha256=assignment.initial_state_sha256,
        partition=assignment.partition,
        kind=assignment.kind,
        goal=assignment.goal,
        binding_sha256=assignment.binding_sha256,
        candidate_index=assignment.candidate_index,
        candidate_sha256="f" * 64,
        candidate_feature_sha256=assignment.candidate_feature_sha256,
    )

    with pytest.raises(RedPartyDevelopmentOutcomeRuntimeError, match="available frozen"):
        bind_red_party_development_outcome_trial(
            question,
            menu,
            wrong,
            party=snapshot.party,
            venue_question_trainee=venue_trainee,
            training_venues=_training_venues(snapshot),
            evolutions={},
            internal_to_national=_red_mapping(),
            dose=RED_PARTY_DEVELOPMENT_OUTCOME_DOSE,
        )


def test_trial_binding_rejects_two_party_members_in_one_level_lineage() -> None:
    snapshot, menu, venue_trainee, question, assignment = _question_and_assignment(
        kind=TrainingChoiceKind.TRAINEE,
        candidate_index=1,
    )
    mapping = _red_mapping()
    start_national = mapping[snapshot.party.members[1].species_id]
    descendant_internal = next(
        internal for internal, national in mapping.items() if national == 131
    )
    ambiguous_party = PartyObservation(
        (
            snapshot.party.members[0],
            snapshot.party.members[1],
            replace(snapshot.party.members[2], species_id=descendant_internal),
        )
    )

    with pytest.raises(RedPartyDevelopmentOutcomeRuntimeError, match="not unique"):
        bind_red_party_development_outcome_trial(
            question,
            menu,
            assignment,
            party=ambiguous_party,
            venue_question_trainee=venue_trainee,
            training_venues=_training_venues(snapshot),
            evolutions={
                start_national: (
                    Evolution(start_national, 131, EvolutionMethod.LEVEL, 31),
                )
            },
            internal_to_national=mapping,
            dose=RED_PARTY_DEVELOPMENT_OUTCOME_DOSE,
        )


def test_lineage_excludes_stone_and_trade_branches() -> None:
    mapping = _red_mapping()
    source = 22
    national = mapping[source]

    lineage = automatic_level_evolution_lineage(
        source,
        evolutions={
            national: (
                Evolution(national, 131, EvolutionMethod.LEVEL, 31),
                Evolution(national, 132, EvolutionMethod.STONE, 10),
                Evolution(national, 133, EvolutionMethod.TRADE),
            )
        },
        internal_to_national=mapping,
    )

    nationals = {mapping[internal] for internal in lineage}
    assert nationals == {national, 131}


def test_lineage_rejects_a_mapping_that_is_not_the_red_cartridge_mapping() -> None:
    with pytest.raises(RedPartyDevelopmentOutcomeRuntimeError, match="mapping is invalid"):
        automatic_level_evolution_lineage(
            22,
            evolutions={},
            internal_to_national={22: 1},
        )


class _FakeActionExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, action: MacroAction) -> object:
        del action
        self.calls += 1
        return None


def test_action_budget_refuses_before_the_first_excess_input() -> None:
    delegate = _FakeActionExecutor()
    executor = BoundedActionExecutor(delegate, maximum_actions=2)
    action = MacroAction(MacroActionKind.CONFIRM)

    executor.execute(action)
    executor.execute(action)
    with pytest.raises(RedPartyDevelopmentOutcomeRuntimeError, match="action budget"):
        executor.execute(action)

    assert executor.actions_executed == 2
    assert delegate.calls == 2


class _FakeEmulator:
    def __init__(self) -> None:
        self.frame_count = 100
        self.marker = "delegated"

    def tick(self, frames: int) -> None:
        self.frame_count += frames


def test_frame_budget_refuses_before_the_first_excess_tick_and_delegates_reads() -> None:
    delegate = _FakeEmulator()
    emulator = FrameBudgetEmulator(delegate, maximum_frames=10)

    emulator.tick(6)
    assert emulator.marker == "delegated"
    with pytest.raises(RedPartyDevelopmentOutcomeRuntimeError, match="frame budget"):
        emulator.tick(5)

    assert emulator.frames_executed == 6
    assert delegate.frame_count == 106
