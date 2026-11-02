from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.red_early_game_skill as early
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_goal_context import _build_provider
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)


def profile(parameters=None):
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="short-errand", providers=(
            (GoalKind.ADVANCE_STORY, RedGoalMechanic.OAKS_ERRAND, parameters or {}),
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.CENTER_RESTORE, {}),
            (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}))))


def test_profile_cannot_expand_into_other_story_stages():
    assert profile().providers[0].mechanic is RedGoalMechanic.OAKS_ERRAND
    with pytest.raises(RedGoalContextProfileError):
        profile({"trainer_objective": "defeat_champion"})


def test_narrow_goal_reuses_existing_chapter_and_declares_teacher_control(monkeypatch):
    calls, latched = [], []
    raw = NS(game_started=True, battle_state=0, party_hp=(20,))
    reader = NS(
        read=lambda: raw,
        read_opening_control_state=lambda _: NS(
            phase=early.OpeningPhase.STARTER_OBTAINED,
            all_controls_allowed=True,
            first_party_species=early.SQUIRTLE_SPECIES_ID,
        ),
        read_oaks_errand_state=lambda _: NS(
            battled_rival=False, got_oaks_parcel=False, oak_got_parcel=False,
            got_pokedex=False, parcel_in_bag=False,
        ),
        read_input_readiness=lambda: NS(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    runtime = NS(emulator=NS(pressed_buttons=frozenset()), reader=reader,
                 observer=NS(latch_verified_facts=latched.append))
    actions = object()

    def chapter(emulator, reader, counted):
        assert emulator is runtime.emulator and reader is runtime.reader
        assert counted.delegate is actions
        calls.append("existing-errand")
        return NS(passed=True, actions_executed=10, frames_executed=240,
                  public_dict=lambda: {"passed": True})

    monkeypatch.setattr(early, "run_oaks_errand_chapter", chapter)
    skill = early.build_red_oaks_errand_skill(
        runtime.emulator, runtime.reader, actions, runtime.observer)
    state = GameState(GameMode.OVERWORLD, skill.required_facts, location="oaks_lab")
    assert skill.availability(state).executable
    assert not skill.availability(replace(state, location="pallet_town")).executable
    assert not skill.availability(replace(state, facts=frozenset())).executable
    assert not skill.availability(replace(state,
        facts=state.facts | skill.expected_facts)).executable
    # A semantic location alone must not bypass the real native-entry guard.
    raw.battle_state = 1
    assert not skill.availability(state).executable
    raw.battle_state = 0
    result = skill.execute()
    assert calls == ["existing-errand"] and latched == [skill.expected_facts]
    assert result.evidence["mechanic_execution"] == "teacher_authored_bounded_chapter"
    assert result.evidence["automatic_objective_ids"] == []
    assert skill.objective_id == "receive_pokedex"
    assert _build_provider(runtime, profile().providers[0], actions).kind is GoalKind.ADVANCE_STORY
