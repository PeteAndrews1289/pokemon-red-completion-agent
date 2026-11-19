from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_search_memory import GoalSearchHistory
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.red_fishing_survey_history import (
    MODE, declared_survey_comparison, observe_rebound_effort, previous_successful_survey,
)


SCOPE = dict(partition="development", diagnostic_only=True, new_campaign=False,
             copy_back=False, fit_allowed=False, official_acceptance=False)


@pytest.mark.parametrize("change", [
    {MODE: 1}, {"partition": "train"}, {"partition": "test"}, {"diagnostic_only": False},
    {"new_campaign": True}, {"copy_back": True}, {"fit_allowed": True}, {"official_acceptance": True},
    {"actual_gameplay_resume_authorized": True}, {"matched_collection_order": {}},
])
def test_copy_scope(change):
    with pytest.raises(ValueError):
        declared_survey_comparison({**SCOPE, MODE: True, **change})


def test_legacy_does_not_read_a_predecessor():
    assert not declared_survey_comparison({})
    assert previous_successful_survey("/absent", {}, b"") is None


@dataclass(frozen=True)
class Candidate:
    search_history: GoalSearchHistory
    features: object


@dataclass(frozen=True)
class Menu:
    candidates: tuple
    available_indices: tuple


@dataclass(frozen=True)
class Options:
    menu: Menu
    bindings: tuple


def options(*, historical=None, travel=0, indices=(0,)):
    fish = Candidate(historical or GoalSearchHistory(), SimpleNamespace(
        travel_effort=travel, kind=LivingDexOptionKind.ACQUIRE))
    other = Candidate(GoalSearchHistory(), SimpleNamespace(
        travel_effort=0, kind=LivingDexOptionKind.ACQUIRE))
    return Options(Menu((fish, other), indices), tuple(
        SimpleNamespace(binding_ref=ref, kind=GoalKind.ACQUIRE_SPECIES) for ref in ("fish", "other")))


def snapshot(*, state="terminal", balls=((3, 4),), slots=2, battle=0):
    return SimpleNamespace(sha256=state, facts=dict(input_ready=True, buttons_released=True,
        battle_state=battle, diagnostics=dict(bag_items=balls, immediate_capture_slots=slots)))


SURVEY = dict(state="terminal", site_sha256="site", live_binding="fish",
              source_outcome_sha256="prior", actions=33, frames=560)


@pytest.mark.parametrize("menu,live", [
    (options(), snapshot(state="later")), (options(), snapshot(balls=((1, 1),))),
    (options(), snapshot(slots=0)), (options(), snapshot(battle=1)),
    (options(indices=(1,)), snapshot()), (options(travel=0.01), snapshot()),
    (options(historical=GoalSearchHistory(1, 1, 40, 500)), snapshot()),
])
def test_fresh_executable_uncredited_entry_required(menu, live):
    result, trace = observe_rebound_effort(menu, live, SURVEY)
    assert result is menu and trace is None


def test_full_menu_unchanged_except_measured_previous_survey():
    live, original = snapshot(), options()
    changed, receipt = observe_rebound_effort(original, live, SURVEY)
    assert changed.bindings is original.bindings
    assert changed.menu.candidates[1] is original.menu.candidates[1]
    assert original.menu.candidates[0].search_history == GoalSearchHistory()
    assert changed.menu.candidates[0].search_history == GoalSearchHistory(1, 0, 33, 560)
    assert receipt["previous_verification"] == "succeeded"
    assert not receipt["cumulative_memory_written"]
    assert observe_rebound_effort(changed, live, SURVEY) == (changed, None)
    wrong = replace(original, bindings=(original.bindings[1], original.bindings[0]))
    assert observe_rebound_effort(wrong, live, SURVEY) == (wrong, None)
