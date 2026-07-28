from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.quest import (
    Objective,
    QuestGraph,
    QuestGraphValidationError,
    Specialist,
)
from pokemon_red_completion.route import COMPLETION_QUEST, HALL_OF_FAME_FACT


def _objective(
    objective_id: str,
    *,
    prerequisites: frozenset[str] = frozenset(),
    priority: int = 100,
) -> Objective:
    return Objective(
        id=objective_id,
        title=objective_id.replace("_", " ").title(),
        completion_facts=frozenset({f"done:{objective_id}"}),
        specialist=Specialist.INTERACTION,
        prerequisites=prerequisites,
        priority=priority,
    )


def _state_after(graph: QuestGraph, *objective_ids: str) -> GameState:
    facts = frozenset(
        fact
        for objective_id in objective_ids
        for fact in graph.objective(objective_id).completion_facts
    )
    return GameState(mode=GameMode.OVERWORLD, facts=facts)


def test_game_state_is_immutable_and_normalizes_facts() -> None:
    source = {"badge:boulder"}
    state = GameState(mode=GameMode.OVERWORLD, facts=source, location="pewter_city")
    source.add("badge:cascade")

    assert state.facts == frozenset({"badge:boulder"})
    assert state.with_facts("badge:cascade").facts == frozenset(
        {"badge:boulder", "badge:cascade"}
    )
    assert state.facts == frozenset({"badge:boulder"})
    with pytest.raises(FrozenInstanceError):
        state.location = "cerulean_city"  # type: ignore[misc]


def test_duplicate_objective_ids_are_rejected() -> None:
    with pytest.raises(QuestGraphValidationError, match="duplicate objective ids: start"):
        QuestGraph((_objective("start"), _objective("start")))


def test_missing_prerequisite_is_rejected() -> None:
    with pytest.raises(
        QuestGraphValidationError,
        match=r"missing prerequisite objectives: finish -> absent",
    ):
        QuestGraph((_objective("finish", prerequisites=frozenset({"absent"})),))


def test_cycles_are_rejected_with_the_cycle_path() -> None:
    with pytest.raises(
        QuestGraphValidationError,
        match=r"objective cycle detected: alpha -> beta -> gamma -> alpha",
    ):
        QuestGraph(
            (
                _objective("alpha", prerequisites=frozenset({"beta"})),
                _objective("beta", prerequisites=frozenset({"gamma"})),
                _objective("gamma", prerequisites=frozenset({"alpha"})),
            )
        )


def test_next_objective_is_deterministic_by_priority_then_id() -> None:
    graph = QuestGraph(
        (
            _objective("zebra", prerequisites=frozenset({"root"}), priority=20),
            _objective("beta", prerequisites=frozenset({"root"}), priority=10),
            _objective("root", priority=0),
            _objective("alpha", prerequisites=frozenset({"root"}), priority=10),
        )
    )
    at_branch = _state_after(graph, "root")

    assert [objective.id for objective in graph.available_objectives(at_branch)] == [
        "alpha",
        "beta",
        "zebra",
    ]
    assert graph.next_objective(at_branch).id == "alpha"  # type: ignore[union-attr]

    after_alpha = at_branch.with_facts("done:alpha")
    assert graph.next_objective(after_alpha).id == "beta"  # type: ignore[union-attr]


def test_completion_route_allows_flexible_midgame_branches() -> None:
    at_celadon = _state_after(
        COMPLETION_QUEST,
        "power_on",
        "begin_adventure",
        "choose_starter",
        "receive_pokedex",
        "reach_pewter",
        "defeat_brock",
        "reach_cerulean",
        "help_bill",
        "defeat_misty",
        "reach_vermilion",
        "obtain_cut",
        "defeat_surge",
        "reach_lavender",
        "reach_celadon",
    )

    available = {
        objective.id for objective in COMPLETION_QUEST.available_objectives(at_celadon)
    }
    assert {"clear_rocket_hideout", "defeat_erika", "reach_saffron"} <= available

    after_erika = at_celadon.with_facts("badge:rainbow")
    still_available = {
        objective.id for objective in COMPLETION_QUEST.available_objectives(after_erika)
    }
    assert {"clear_rocket_hideout", "reach_saffron"} <= still_available


def test_hall_of_fame_is_the_only_terminal_and_requires_champion() -> None:
    assert [objective.id for objective in COMPLETION_QUEST.terminal_objectives()] == [
        "enter_hall_of_fame"
    ]

    all_but_terminal = _state_after(
        COMPLETION_QUEST,
        *(
            objective.id
            for objective in COMPLETION_QUEST
            if objective.id != "enter_hall_of_fame"
        ),
    )
    assert not COMPLETION_QUEST.is_complete(all_but_terminal)
    terminal = COMPLETION_QUEST.next_objective(all_but_terminal)
    assert terminal is not None
    assert terminal.id == "enter_hall_of_fame"

    complete = GameState(
        mode=GameMode.HALL_OF_FAME,
        facts=all_but_terminal.facts.union({HALL_OF_FAME_FACT}),
    )
    assert COMPLETION_QUEST.is_complete(complete)
    assert COMPLETION_QUEST.next_objective(complete) is None
    assert complete.mode is GameMode.HALL_OF_FAME
