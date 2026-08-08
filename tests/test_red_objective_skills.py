from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.red_objective_skills import (
    PokemonTowerObjectiveSkill,
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
