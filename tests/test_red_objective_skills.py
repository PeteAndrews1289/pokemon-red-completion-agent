from __future__ import annotations

from dataclasses import dataclass

import pytest

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.red_objective_skills import (
    CrossVictoryRoadObjectiveSkill,
    DefeatAgathaObjectiveSkill,
    DefeatBlaineObjectiveSkill,
    DefeatBrunoObjectiveSkill,
    DefeatChampionObjectiveSkill,
    DefeatErikaObjectiveSkill,
    DefeatGiovanniObjectiveSkill,
    DefeatKogaObjectiveSkill,
    DefeatLanceObjectiveSkill,
    DefeatLoreleiObjectiveSkill,
    DefeatSabrinaObjectiveSkill,
    EnterHallOfFameObjectiveSkill,
    LiberateSilphObjectiveSkill,
    ObtainSecretKeyObjectiveSkill,
    ObtainStrengthObjectiveSkill,
    ObtainSurfObjectiveSkill,
    PokemonTowerObjectiveSkill,
    ReachCinnabarObjectiveSkill,
    ReachFuchsiaObjectiveSkill,
    ReachSaffronObjectiveSkill,
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
    koga = DefeatKogaObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    strength = ObtainStrengthObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    erika = DefeatErikaObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    saffron = ReachSaffronObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    silph = LiberateSilphObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    sabrina = DefeatSabrinaObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    cinnabar = ReachCinnabarObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    mansion = ObtainSecretKeyObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    blaine = DefeatBlaineObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    giovanni = DefeatGiovanniObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    victory_road = CrossVictoryRoadObjectiveSkill(  # type: ignore[arg-type]
        emulator, reader, executor
    )
    lorelei = DefeatLoreleiObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    bruno = DefeatBrunoObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    agatha = DefeatAgathaObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    lance = DefeatLanceObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    champion = DefeatChampionObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
    hall = EnterHallOfFameObjectiveSkill(emulator, reader, executor)  # type: ignore[arg-type]
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
    surf_ready = fuchsia_center.with_facts("move:surf_available", "item:gold_teeth")
    assert koga.availability(surf_ready).executable
    assert strength.availability(surf_ready).executable
    post_strength = surf_ready.with_facts("badge:soul", "move:strength_available")
    assert erika.availability(post_strength).executable
    post_erika = GameState(
        GameMode.OVERWORLD,
        facts=frozenset({"badge:rainbow"}),
        location="celadon_pokecenter",
    )
    assert saffron.availability(post_erika).executable
    saffron_center = GameState(
        GameMode.OVERWORLD,
        facts=frozenset({"location:saffron_city"}),
        location="saffron_pokecenter",
    )
    assert silph.availability(saffron_center).executable
    post_silph = saffron_center.with_facts("story:silph_co_liberated")
    assert sabrina.availability(post_silph).executable
    post_sabrina = post_silph.with_facts("badge:marsh", "move:surf_available")
    assert cinnabar.availability(post_sabrina).executable
    cinnabar_center = post_sabrina.with_facts("location:cinnabar_island")
    cinnabar_center = GameState(
        cinnabar_center.mode,
        cinnabar_center.facts,
        location="cinnabar_pokecenter",
    )
    assert mansion.availability(cinnabar_center).executable
    post_mansion = cinnabar_center.with_facts("item:secret_key")
    assert blaine.availability(post_mansion).executable
    assert not mansion.availability(post_mansion).executable
    post_blaine = post_mansion.with_facts("badge:volcano")
    assert giovanni.availability(post_blaine).executable
    assert not blaine.availability(post_blaine).executable
    post_giovanni = GameState(
        GameMode.OVERWORLD,
        facts=post_blaine.with_facts("badge:earth", "move:strength_available").facts,
        location="viridian_pokecenter",
    )
    assert victory_road.availability(post_giovanni).executable
    assert not giovanni.availability(post_giovanni).executable
    indigo = GameState(
        GameMode.OVERWORLD,
        facts=post_giovanni.with_facts("story:victory_road_cleared").facts,
        location="indigo_plateau_lobby",
    )
    assert lorelei.availability(indigo).executable
    bruno_room = GameState(
        GameMode.OVERWORLD,
        facts=indigo.with_facts("league:lorelei_defeated").facts,
        location="brunos_room",
    )
    assert bruno.availability(bruno_room).executable
    agatha_room = GameState(
        GameMode.OVERWORLD,
        facts=bruno_room.with_facts("league:bruno_defeated").facts,
        location="agathas_room",
    )
    assert agatha.availability(agatha_room).executable
    lance_room = GameState(
        GameMode.OVERWORLD,
        facts=agatha_room.with_facts("league:agatha_defeated").facts,
        location="lances_room",
    )
    assert lance.availability(lance_room).executable
    champion_room = GameState(
        GameMode.OVERWORLD,
        facts=lance_room.with_facts("league:lance_defeated").facts,
        location="champions_room",
    )
    assert champion.availability(champion_room).executable
    ceremony = champion_room.with_facts("league:champion_defeated")
    assert hall.availability(ceremony).executable
    assert not champion.availability(ceremony).executable


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


@pytest.mark.parametrize(
    ("skill_type", "runner_name", "objective_id", "actions", "frames"),
    (
        (DefeatKogaObjectiveSkill, "run_koga_chapter", "defeat_koga", 800, 90_000),
        (
            ObtainStrengthObjectiveSkill,
            "run_strength_chapter",
            "obtain_strength",
            300,
            40_000,
        ),
        (DefeatErikaObjectiveSkill, "run_erika_chapter", "defeat_erika", 2_000, 300_000),
        (
            ReachSaffronObjectiveSkill,
            "run_saffron_chapter",
            "reach_saffron",
            1_000,
            150_000,
        ),
        (
            LiberateSilphObjectiveSkill,
            "run_silph_chapter",
            "liberate_silph",
            4_000,
            700_000,
        ),
        (
            ReachCinnabarObjectiveSkill,
            "run_cinnabar_chapter",
            "reach_cinnabar",
            2_500,
            350_000,
        ),
        (
            ObtainSecretKeyObjectiveSkill,
            "run_mansion_secret_key_chapter",
            "obtain_secret_key",
            3_000,
            450_000,
        ),
        (
            DefeatBlaineObjectiveSkill,
            "run_blaine_after_mansion_chapter",
            "defeat_blaine",
            600_000,
            80_000_000,
        ),
        (
            DefeatGiovanniObjectiveSkill,
            "run_giovanni_chapter",
            "defeat_giovanni",
            2_000,
            300_000,
        ),
        (
            CrossVictoryRoadObjectiveSkill,
            "run_victory_road_chapter",
            "cross_victory_road",
            4_000,
            500_000,
        ),
        (DefeatLoreleiObjectiveSkill, "run_lorelei_chapter", "defeat_lorelei", 800, 100_000),
        (DefeatBrunoObjectiveSkill, "run_bruno_chapter", "defeat_bruno", 800, 100_000),
        (DefeatAgathaObjectiveSkill, "run_agatha_chapter", "defeat_agatha", 800, 100_000),
        (DefeatLanceObjectiveSkill, "run_lance_chapter", "defeat_lance", 800, 100_000),
        (
            DefeatChampionObjectiveSkill,
            "run_champion_chapter",
            "defeat_champion",
            800,
            100_000,
        ),
        (
            EnterHallOfFameObjectiveSkill,
            "run_hall_of_fame_chapter",
            "enter_hall_of_fame",
            100,
            20_000,
        ),
    ),
)
def test_red_fuchsia_followup_skills_match_graph_and_preserve_evidence(
    monkeypatch,
    skill_type,
    runner_name: str,
    objective_id: str,
    actions: int,
    frames: int,
) -> None:
    def fake_run(emulator, reader, executor, **kwargs):
        return _Report(actions_executed=actions, frames_executed=frames)

    monkeypatch.setattr(
        f"pokemon_red_completion.red_objective_skills.{runner_name}",
        fake_run,
    )
    skill = skill_type(object(), object(), object())

    result = skill.execute()

    objective = COMPLETION_QUEST.objective(objective_id)
    assert skill.specialist is objective.specialist
    assert skill.expected_facts == objective.completion_facts
    assert result.actions_executed == actions
    assert result.frames_executed == frames


def test_red_sabrina_skill_composes_dojo_curriculum_and_gym(monkeypatch) -> None:
    calls: list[str] = []

    @dataclass
    class _PassedReport(_Report):
        passed: bool = True

    def fake_dojo(emulator, reader, executor, *, timing):
        calls.append("dojo")
        return _PassedReport(actions_executed=700, frames_executed=80_000)

    def fake_sabrina(emulator, reader, executor, *, timing):
        calls.append("sabrina")
        return _PassedReport(actions_executed=900, frames_executed=120_000)

    monkeypatch.setattr(
        "pokemon_red_completion.red_objective_skills.run_dojo_chapter",
        fake_dojo,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_objective_skills.run_sabrina_chapter",
        fake_sabrina,
    )
    skill = DefeatSabrinaObjectiveSkill(object(), object(), object())

    result = skill.execute()

    objective = COMPLETION_QUEST.objective("defeat_sabrina")
    assert skill.specialist is objective.specialist
    assert skill.expected_facts == objective.completion_facts
    assert result.actions_executed == 1_600
    assert result.frames_executed == 200_000
    assert result.evidence["status"] == "ok"
    assert calls == ["dojo", "sabrina"]
