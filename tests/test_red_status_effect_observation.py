from copy import deepcopy

import pytest
from test_red_status_closed_loop_returns import episode

from pokemon_red_completion.red_status_effect_observation import observe_status_effect


def boundary(*args, **kwargs):
    e = episode(*args, **kwargs)
    identity = {"opponent_party_position": 0, "opponent_species_id": 173,
                "active_party_slot": 1}
    step = e["decisions"][0]
    step["state_before"] = {**step["state_before"], **identity}
    step["state_after"] = deepcopy(step["state_before"])
    return e


@pytest.mark.parametrize("move,status", [(79, "sleep"), (86, "paralysis"), (77, "poison")])
def test_new_affliction_and_no_net_change_are_observations_not_success(move, status):
    e = boundary(move, None, status)
    original = deepcopy(e)
    result = observe_status_effect(e)
    assert result["net_change"] == 1
    assert result["application_success"] is None
    assert e == original
    assert observe_status_effect(boundary(move))["net_change"] == 0
    assert observe_status_effect(boundary(move, "paralysis", "paralysis"))["net_change"] == 0


@pytest.mark.parametrize("new", [None, "sleep", "paralysis"])
def test_sleep_expiry_duration_is_unknown(new):
    assert observe_status_effect(boundary(79, "sleep", new))["net_change"] is None


def test_confusion_reapplication_is_not_fabricated():
    e = boundary(109)
    assert observe_status_effect(e)["net_change"] is None
    context = e["decisions"][0]["observation"]["features"]["battle"]["status_context"]
    context["opponent_confused"] = False
    assert observe_status_effect(e)["net_change"] == 1
    e["final_observation"]["features"]["battle"]["status_context"]["opponent_confused"] = False
    assert observe_status_effect(e)["net_change"] == 0


def test_accuracy_is_measured_with_range_checks():
    e = boundary(28)
    stages = e["final_observation"]["features"]["battle"]["status_context"]["opponent_stages"]
    assert observe_status_effect(e)["net_change"] == 0
    stages[4] = -1
    assert observe_status_effect(e)["net_change"] == 1
    stages[4] = 1
    assert observe_status_effect(e)["net_change"] is None
    stages[4] = -7
    assert observe_status_effect(e)["net_change"] is None
    stages[4] = False
    assert observe_status_effect(e)["net_change"] is None


@pytest.mark.parametrize("move,family", [(105, "heal"), (156, "rest"), (50, "disable"),
                                       (33, "unsupported")])
def test_unobservable_families_remain_unknown(move, family):
    e = boundary(move)
    e["decisions"][0]["state_after"]["party_hp"] = [20]
    result = observe_status_effect(e)
    assert result["family"] == family
    assert result["net_change"] is None


def test_suppression_not_failure_and_execution_boolean_required():
    result = observe_status_effect(boundary(executed=False))
    assert result["kind"] == "suppressed" and result["net_change"] is None
    with pytest.raises(ValueError, match="execution boolean"):
        observe_status_effect(boundary(executed=1))


@pytest.mark.parametrize("key", ["opponent_party_position", "opponent_species_id",
                               "active_party_slot"])
def test_changed_or_missing_boundary_identity_is_unknown(key):
    e = boundary(79, None, "sleep")
    e["decisions"][0]["state_after"][key] += 1
    assert observe_status_effect(e)["net_change"] is None
    del e["decisions"][0]["state_after"][key]
    assert observe_status_effect(e)["net_change"] is None


def test_terminal_or_intervening_transition_is_unknown():
    e = boundary(79, None, "sleep")
    step = deepcopy(e["decisions"][0])
    step["observation"] = deepcopy(e["final_observation"])
    e["decisions"].append(step)
    assert observe_status_effect(e)["net_change"] == 1
    step["state_before"]["party_hp"] = [49]
    assert observe_status_effect(e)["net_change"] is None
    e["decisions"].pop()
    e["final_observation"]["features"]["battle"]["active"] = False
    assert observe_status_effect(e)["net_change"] is None


def test_missing_or_changed_semantic_opponent_is_unknown():
    e = boundary(79, None, "sleep")
    e["final_observation"]["features"]["battle"]["opponent_species_ref"] = None
    assert observe_status_effect(e)["net_change"] is None
    e["final_observation"]["features"]["battle"] = None
    assert observe_status_effect(e)["net_change"] is None
