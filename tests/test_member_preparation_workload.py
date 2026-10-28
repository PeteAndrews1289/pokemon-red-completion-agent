from dataclasses import replace

import pytest
from test_red_live_option_menu import _binding, _situation

from pokemon_red_completion.goal_manager import GoalKind, GoalOpportunity, GoalAvailability, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
from pokemon_red_completion.player_option_preparation import OptionPreparation
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionMenuError, build_red_live_option_set, supplemental_live_option,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


DESCRIPTOR = OptionPreparation(15, 18, 1534, .8, 1., False, True, 18)


def build(version, *, descriptor=DESCRIPTOR, explicit=None):
    calls = []
    develop = _binding(GoalKind.DEVELOP_TEAM, binding_ref="private-member", calls=calls)
    restore = _binding(GoalKind.RESTORE_TEAM, binding_ref="private-center", calls=calls)
    bindings = (develop, restore)
    ordinary = GoalBindingSet(tuple(x.opportunity for x in bindings), bindings)
    kwargs = dict(situation=_situation(resources=.1), binding_set=ordinary,
        supplements=(), model_feature_version=version, ordering_seed_sha256="a"*64,
        economy_snapshot=EconomySnapshot(1000, ()), target_cash=0)
    if explicit is not None:
        base = build_red_live_option_set(**kwargs)
        candidate = next(x for x in base.menu.candidates if x.binding_ref == develop.binding_ref)
        masked = GoalOpportunity('masked', GoalKind.EXPLORE, GoalAvailability.UNAVAILABLE,
                                 unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
        kwargs.update(binding_set=GoalBindingSet((restore.opportunity, masked), (restore,)),
            supplements=(supplemental_live_option(develop, replace(candidate, level_workload=explicit)),))
    kwargs['preparations'] = {develop.binding_ref: descriptor} if descriptor else {}
    options = build_red_live_option_set(**kwargs)
    index = next(i for i, x in enumerate(options.menu.candidates) if x.binding_ref == develop.binding_ref)
    assert options.binding(index) is develop
    assert calls == []
    return options, index


def test_v9_member_preparation_exposes_the_already_measured_workload():
    options, i = build(9)
    row = options.menu.candidates[i]
    assert row.preparation is DESCRIPTOR
    assert row.level_workload == OptionLevelWorkload(15, 18, 1534)
    assert options.menu.candidate_vector(i, feature_version=9)[-5:] == (1., .15, .18, .03, 1534/2_000_000)


@pytest.mark.parametrize("version", [7, 8])
def test_legacy_member_preparation_keeps_its_old_vector(version):
    old, j = build(version)
    new, i = build(9)
    assert old.menu.candidates[j].level_workload is None
    vector = old.menu.candidate_vector(j, feature_version=version)
    assert new.menu.candidate_vector(i, feature_version=9)[:len(vector)] == vector


def test_no_descriptor_does_not_invent_a_training_workload():
    options, i = build(9, descriptor=None)
    assert options.menu.candidates[i].level_workload is None


def test_matching_explicit_workload_is_preserved():
    options, i = build(9, explicit=OptionLevelWorkload(15, 18, 1534))
    assert options.menu.candidates[i].level_workload == OptionLevelWorkload(15, 18, 1534)


@pytest.mark.parametrize("explicit", [OptionLevelWorkload(15, 19, 2000),
    OptionLevelWorkload(14, 18, 2000), OptionLevelWorkload(15, 18, 1535)])
def test_conflicting_known_workload_is_rejected_before_any_execution(explicit):
    with pytest.raises(RedLiveOptionMenuError, match="workload"):
        build(9, explicit=explicit)
