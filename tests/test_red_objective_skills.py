from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.red_objective_skills import (
    ObtainSurfObjectiveSkill,
    PokemonTowerObjectiveSkill,
    ReachFuchsiaObjectiveSkill,
    RocketHideoutObjectiveSkill,
)
from pokemon_red_completion.route import COMPLETION_QUEST


@dataclass
class _Report:
    actions_executed: int = 91
    frames_executed: int = 12_345

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "trainers": 5}


def test_red_hideout_skill_matches_graph_and_preserves_mechanics_evidence(monkeypatch) -> None:
    calls: list[tuple[object, object, object]] = []

    def fake_run(emulator, reader, executor, *, timing):
        calls.append((emulator, reader, executor))
        return _Report()

    monkeypatch.setattr(
        "pokemon_red_completion.red_objective_skills.run_hideout_chapter",
        fake_run,
    )
    emulator = object()
    reader = object()
    executor = object()
    skill = RocketHideoutObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]

    result = skill.execute()

    objective = COMPLETION_QUEST.objective("clear_rocket_hideout")
    assert skill.specialist is objective.specialist
    assert skill.expected_facts == objective.completion_facts
    assert skill.additional_effect_facts == frozenset({"item:silph_scope"})
    assert result.actions_executed == 91
    assert result.frames_executed == 12_345
    assert result.evidence == {"status": "ok", "trainers": 5}
    assert calls == [(emulator, reader, executor)]


def test_red_tower_skill_matches_graph_and_preserves_mechanics_evidence(monkeypatch) -> None:
    calls: list[tuple[object, object, object]] = []

    def fake_run(emulator, reader, executor, *, timing):
        calls.append((emulator, reader, executor))
        return _Report(actions_executed=1_487, frames_executed=222_333)

    monkeypatch.setattr(
        "pokemon_red_completion.red_objective_skills.run_tower_chapter",
        fake_run,
    )
    emulator = object()
    reader = object()
    executor = object()
    skill = PokemonTowerObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]

    result = skill.execute()

    objective = COMPLETION_QUEST.objective("rescue_fuji")
    assert skill.specialist is objective.specialist
    assert skill.expected_facts == objective.completion_facts
    assert skill.additional_effect_facts == frozenset()
    assert result.actions_executed == 1_487
    assert result.frames_executed == 222_333
    assert result.evidence == {"status": "ok", "trainers": 5}
    assert calls == [(emulator, reader, executor)]


def test_red_fuchsia_skill_matches_graph_and_preserves_mechanics_evidence(monkeypatch) -> None:
    calls: list[tuple[object, object, object]] = []

    def fake_run(emulator, reader, executor, *, timing):
        calls.append((emulator, reader, executor))
        return _Report(actions_executed=3_200, frames_executed=444_555)

    monkeypatch.setattr(
        "pokemon_red_completion.red_objective_skills.run_fuchsia_chapter",
        fake_run,
    )
    emulator = object()
    reader = object()
    executor = object()
    skill = ReachFuchsiaObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]

    result = skill.execute()

    objective = COMPLETION_QUEST.objective("reach_fuchsia")
    assert skill.specialist is objective.specialist
    assert skill.expected_facts == objective.completion_facts
    assert skill.additional_effect_facts == frozenset()
    assert result.actions_executed == 3_200
    assert result.frames_executed == 444_555
    assert result.evidence == {"status": "ok", "trainers": 5}
    assert calls == [(emulator, reader, executor)]


def test_red_objective_skills_expose_semantic_starting_affordances() -> None:
    emulator = object()
    reader = object()
    executor = object()
    hideout = RocketHideoutObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    tower = PokemonTowerObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    fuchsia = ReachFuchsiaObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    safari = ObtainSurfObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    celadon = GameState(
        GameMode.OVERWORLD,
        facts=frozenset({"item:silph_scope"}),
        location="celadon_pokecenter",
    )
    lavender = GameState(
        GameMode.OVERWORLD,
        facts=frozenset({"item:poke_flute"}),
        location="lavender_pokecenter",
    )
    fuchsia_center = GameState(
        GameMode.OVERWORLD,
        facts=frozenset({"location:fuchsia_city"}),
        location="fuchsia_pokecenter",
    )

    assert tower.availability(celadon).executable
    assert not hideout.availability(celadon).executable
    assert fuchsia.availability(lavender).executable
    assert not tower.availability(lavender).executable
    assert safari.availability(fuchsia_center).executable


def test_red_safari_skill_matches_graph_and_declares_gold_teeth_effect(monkeypatch) -> None:
    calls: list[tuple[object, object, object]] = []

    def fake_run(emulator, reader, executor, *, timing):
        calls.append((emulator, reader, executor))
        return _Report(actions_executed=1_111, frames_executed=222_222)

    monkeypatch.setattr(
        "pokemon_red_completion.red_objective_skills.run_safari_chapter",
        fake_run,
    )
    emulator = object()
    reader = object()
    executor = object()
    skill = ObtainSurfObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]

    result = skill.execute()

    objective = COMPLETION_QUEST.objective("obtain_surf")
    assert skill.specialist is objective.specialist
    assert skill.expected_facts == objective.completion_facts
    assert skill.additional_effect_facts == frozenset({"item:gold_teeth"})
    assert result.actions_executed == 1_111
    assert result.frames_executed == 222_222
    assert calls == [(emulator, reader, executor)]
