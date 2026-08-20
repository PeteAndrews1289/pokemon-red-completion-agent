from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.objective_skills import ObjectiveSkillRegistry
from pokemon_red_completion.play import QUALIFIED_OBJECTIVE_SEQUENCE
from pokemon_red_completion.red_early_game_skill import (
    EARLY_GAME_AUTOMATIC_OBJECTIVE_IDS,
    EARLY_GAME_OBJECTIVE_IDS,
    EARLY_GAME_VERIFIED_FACTS,
    EarlyGameThroughCeladonObjectiveSkill,
    run_early_game_composite,
)
from pokemon_red_completion.route import COMPLETION_QUEST


@dataclass
class _Emulator:
    frame_count: int = 100
    pressed_buttons: tuple[str, ...] = ()


@dataclass
class _Executor:
    def execute(self, action):
        return action


@dataclass
class _Observer:
    latched: frozenset[str] = frozenset()

    def latch_verified_facts(self, facts: frozenset[str]) -> None:
        self.latched = facts


def test_early_game_composite_declares_one_dispatch_and_every_automatic_objective() -> None:
    assert QUALIFIED_OBJECTIVE_SEQUENCE[:14] == EARLY_GAME_OBJECTIVE_IDS
    assert QUALIFIED_OBJECTIVE_SEQUENCE[1:14] == EARLY_GAME_AUTOMATIC_OBJECTIVE_IDS
    assert (
        frozenset(
            fact
            for objective_id in EARLY_GAME_OBJECTIVE_IDS
            for fact in COMPLETION_QUEST.objective(objective_id).completion_facts
        )
        == EARLY_GAME_VERIFIED_FACTS
    )


def test_early_game_skill_is_available_only_at_the_untouched_boot_boundary(monkeypatch) -> None:
    emulator = _Emulator()
    observer = _Observer()
    skill = EarlyGameThroughCeladonObjectiveSkill(
        "private.gb",
        emulator,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        _Executor(),  # type: ignore[arg-type]
        observer,  # type: ignore[arg-type]
    )
    ObjectiveSkillRegistry((skill,))

    assert skill.availability(GameState(GameMode.BOOTING)).executable
    assert not skill.availability(
        GameState(GameMode.OVERWORLD, frozenset({"story:adventure_begun"}))
    ).executable

    report = SimpleNamespace(
        verified_facts=EARLY_GAME_VERIFIED_FACTS,
        actions_executed=123,
        frames_executed=456,
        public_dict=lambda: {
            "automatic_objectives": len(EARLY_GAME_AUTOMATIC_OBJECTIVE_IDS),
            "status": "ok",
        },
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_early_game_skill.run_early_game_composite",
        lambda *args, **kwargs: report,
    )

    execution = skill.execute()

    assert observer.latched == EARLY_GAME_VERIFIED_FACTS
    assert execution.actions_executed == 123
    assert execution.frames_executed == 456
    assert execution.evidence["automatic_objectives"] == 13


def test_early_game_composite_runs_the_frozen_chapters_once_and_unions_evidence(
    monkeypatch,
) -> None:
    calls: list[str] = []
    raw_by_name = {name: object() for name in EARLY_GAME_OBJECTIVE_IDS[3:]}
    facts_by_raw = {
        id(raw): COMPLETION_QUEST.objective(objective_id).completion_facts
        for objective_id, raw in zip(
            EARLY_GAME_OBJECTIVE_IDS[3:], raw_by_name.values(), strict=True
        )
    }
    opening = SimpleNamespace(
        passed=True,
        facts=frozenset(
            fact
            for objective_id in EARLY_GAME_OBJECTIVE_IDS[:3]
            for fact in COMPLETION_QUEST.objective(objective_id).completion_facts
        ),
        actions_executed=7,
    )
    oaks = SimpleNamespace(
        passed=True,
        pokedex_received=raw_by_name["receive_pokedex"],
        rival_evidence=SimpleNamespace(rival_victory_snapshot=True),
        saw_trainer_battle=True,
    )
    reports = {
        "pewter": SimpleNamespace(
            passed=True,
            pewter_reached=raw_by_name["reach_pewter"],
            brock_defeated=raw_by_name["defeat_brock"],
        ),
        "cerulean": SimpleNamespace(
            passed=True,
            cerulean_reached=raw_by_name["reach_cerulean"],
        ),
        "cascade": SimpleNamespace(
            passed=True,
            final_raw=raw_by_name["help_bill"],
        ),
        "vermilion": SimpleNamespace(
            passed=True,
            final_raw=raw_by_name["reach_vermilion"],
        ),
        "ss_anne": SimpleNamespace(
            passed=True,
            final_raw=raw_by_name["obtain_cut"],
        ),
        "surge": SimpleNamespace(
            passed=True,
            final_raw=raw_by_name["defeat_surge"],
        ),
        "lavender": SimpleNamespace(
            passed=True,
            final_raw=raw_by_name["reach_lavender"],
        ),
        "celadon": SimpleNamespace(
            passed=True,
            final_raw=raw_by_name["reach_celadon"],
        ),
    }
    # The Cascade terminal verifies both Bill and Misty.
    facts_by_raw[id(raw_by_name["help_bill"])] = (
        COMPLETION_QUEST.objective("help_bill").completion_facts
        | COMPLETION_QUEST.objective("defeat_misty").completion_facts
    )

    def fake(name, result):
        def run(*args, **kwargs):
            calls.append(name)
            return result

        return run

    monkeypatch.setattr(
        "pokemon_red_completion.red_early_game_skill.run_opening_chapter",
        fake("opening", opening),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_early_game_skill.run_oaks_errand_chapter",
        fake("oaks", oaks),
    )
    for name, result in reports.items():
        function_name = "run_ss_anne_chapter" if name == "ss_anne" else f"run_{name}_chapter"
        monkeypatch.setattr(
            f"pokemon_red_completion.red_early_game_skill.{function_name}",
            fake(name, result),
        )
    monkeypatch.setattr(
        "pokemon_red_completion.red_early_game_skill.semantic_facts",
        lambda raw: facts_by_raw[id(raw)],
    )

    report = run_early_game_composite(
        "private.gb",
        emulator=_Emulator(),  # type: ignore[arg-type]
        reader=object(),  # type: ignore[arg-type]
        executor=_Executor(),  # type: ignore[arg-type]
    )

    assert calls == [
        "opening",
        "oaks",
        "pewter",
        "cerulean",
        "cascade",
        "vermilion",
        "ss_anne",
        "surge",
        "lavender",
        "celadon",
    ]
    assert report.passed
    assert report.verified_facts == EARLY_GAME_VERIFIED_FACTS
    assert report.public_dict()["automatic_objectives"] == 13
