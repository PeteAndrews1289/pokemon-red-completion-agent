from dataclasses import replace

import pytest
from test_party_preparation import team

from pokemon_red_completion.party_preparation import PreparationPurpose
from pokemon_red_completion.story_preparation import (
    require_preparation_targets,
    review_story_preparation,
)


def episode(*levels):
    return {
        "decisions": [
            {
                "observation": {
                    "features": {
                        "battle": {
                            "active": True,
                            "kind": "trainer",
                            "opponent_party_count": len(levels),
                            "opponent_remaining_count": len(levels) - i,
                            "opponent_level": level,
                        }
                    }
                }
            }
            for i, level in enumerate(levels)
        ]
    }


def review(members, ep, ready=True):
    return review_story_preparation(members, ep, encounter_ref="fresh", field_ready=ready)


def test_latest_opposition_requests_preparation_then_releases_at_frozen_targets():
    members = team(45, 34, 35, 34)
    result = review(members, episode(44, 45, 46))
    assert result.next_action == "prepare_party"
    targets = dict(result.plan.targets)
    assert targets == {"specimen-2": 42, "specimen-3": 42, "specimen-4": 42}
    with pytest.raises(ValueError, match="automatic party preparation"):
        require_preparation_targets(members, targets)
    require_preparation_targets(team(45, 42, 42, 42), targets)
    assert review(team(45, 42, 42, 42), episode(44, 45, 46)).next_action == "continue_story"


def test_repeated_turns_do_not_weight_the_median():
    ep = episode(20, 40, 42)
    ep["decisions"] = ep["decisions"][:1] * 100 + ep["decisions"][1:]
    result = review(team(40, 30), ep)
    assert result.plan.opposition_level == 40 and result.plan.observed_opponents == 3


@pytest.mark.parametrize(
    "purpose",
    [PreparationPurpose.COLLECTION, PreparationPurpose.UNDECIDED, PreparationPurpose.FIELD_UTILITY],
)
def test_low_catch_does_not_trigger_grinding(purpose):
    members = team(40, 38, 2)
    members = members[:2] + (replace(members[2], purpose=purpose),)
    assert review(members, episode(40)).next_action == "continue_story"


@pytest.mark.parametrize("ready,action", [(False, "settle_battle"), (True, "recover")])
def test_recovery_precedes_preparation_or_story(ready, action):
    members = team(45, 35)
    members = (replace(members[0], observation=replace(members[0].observation, hp=0)), members[1])
    assert review(members, episode(37), ready).next_action == action


def test_missing_evidence_is_not_a_ready_claim():
    assert review(team(40), {"decisions": []}).next_action == "need_opposition_evidence"


@pytest.mark.parametrize(
    "field,value",
    [("opponent_remaining_count", None), ("opponent_party_count", True), ("opponent_level", None)],
)
def test_malformed_semantic_evidence_fails_closed(field, value):
    ep = episode(40)
    ep["decisions"][0]["observation"]["features"]["battle"][field] = value
    with pytest.raises(ValueError):
        review(team(34), ep)


def test_conflicting_repeated_opponent_fails_closed():
    ep = episode(40)
    ep["decisions"] += episode(41)["decisions"]
    with pytest.raises(ValueError, match="conflicting"):
        review(team(34), ep)


def test_roster_change_cannot_satisfy_a_pending_request():
    with pytest.raises(ValueError, match="roster changed"):
        require_preparation_targets(team(45), {"missing": 34})
