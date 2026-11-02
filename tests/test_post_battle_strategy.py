import json
from dataclasses import replace

import numpy as np
import pytest
from test_party_preparation import team

from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalSituation
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
from pokemon_red_completion.party import MoveObservation, StatusCondition
from pokemon_red_completion.party_preparation import (
    ObservedOpponent,
    PreparationAttempt,
    PreparationPurpose,
    build_preparation_plan,
)
from pokemon_red_completion.post_battle_strategy import (
    STRATEGY_SCHEMA,
    BattleAftermath,
    BattleResult,
    PostBattleContext,
    PreparationCostTotals,
    build_post_battle_strategy_menu,
    context_after_recovery,
)


def aftermath(**changes):
    return replace(
        BattleAftermath(
            BattleResult.LOST,
            (50, 54),
            2,
            1,
            (40, 45),
            2,
            2,
            0.0,
            0.5,
            0.25,
            0.2,
            0.1,
            0.02,
        ),
        **changes,
    )


def bindings(*, reverse=False):
    def forbidden(*_):
        pytest.fail("menu/scoring must not execute or verify any provider")

    rows = tuple(
        ExecutableGoalBinding(
            "private:" + kind.value,
            kind,
            0.5,
            0.3,
            forbidden,
            forbidden,
        )
        for kind in (GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM)
    )
    if reverse:
        rows = tuple(reversed(rows))
    return GoalBindingSet(tuple(b.opportunity for b in rows), rows)


def menu(
    *, members=None, attempts=(), battle=None, reverse=False, ready=True, plan=None, costs=None
):
    members = members or team(45, 40)
    plan = plan or build_preparation_plan(
        members,
        (ObservedOpponent("private-encounter", 1, 54),),
    )
    return build_post_battle_strategy_menu(
        bindings=bindings(reverse=reverse),
        situation=GoalSituation(0.2, 0.4, 0.3, 0.1, 0, 0, 0, 0, 0.2),
        battle=battle or aftermath(),
        plan=plan,
        members=members,
        attempts=attempts,
        cumulative_costs=costs
        or PreparationCostTotals(
            len(attempts),
            sum(a.actions for a in attempts),
            sum(a.frames for a in attempts),
            sum(a.elapsed_seconds for a in attempts),
            sum(a.heals for a in attempts),
        ),
        field_ready=ready,
    )


def test_recovery_preserves_loss_and_current_party_is_separate():
    result = menu()
    f = result.context.features()
    assert f["recent.lost"] == 1 and f["recent.hp_fraction"] == 0
    assert f["current.hp_fraction"] == 1 and f["current.fainted_fraction"] == 0
    assert f["current.lowest_combat_level_gap"] == 0.12
    assert f["current.median_combat_level_gap"] == 0.095
    assert f["current.pp_known"] == 0  # Missing maxima do not imply restored PP.
    assert result.remaining_budget == (1,) * 5
    assert result.preparation_block_reason is None


def test_known_pp_is_measured_not_assumed():
    members = team(40)
    member = members[0]
    member = replace(
        member, observation=replace(member.observation, moves=(MoveObservation(33, 5, 10),))
    )
    context = context_after_recovery(aftermath(), (member,))
    assert context.current_pp_fraction == 0.5


def test_current_noncombat_catch_does_not_change_level_gap():
    members = team(45, 40, 2)
    members = (*members[:2], replace(members[2], purpose=PreparationPurpose.COLLECTION))
    c = context_after_recovery(aftermath(), members)
    assert c.current_combat_levels == (45, 40)
    assert c.features()["current.lowest_combat_level_gap"] == 0.12


def test_partial_opposition_is_not_full_roster():
    c = menu(battle=aftermath(opponent_count=6)).context
    assert c.features()["recent.opposition_coverage"] == 2 / 6
    assert c.features()["recent.defeated_fraction"] == 1 / 6


def test_level_gaps_are_signed_and_no_training_preference_is_encoded():
    m = menu(members=team(60, 60))
    assert m.context.features()["current.median_combat_level_gap"] == -0.08
    assert m.preparation_block_reason == "level preparation not needed"
    assert m.bindings.opportunities[1].availability is GoalAvailability.UNAVAILABLE


def test_bound_menu_cannot_promote_an_unavailable_offer():
    m = menu()
    from pokemon_red_completion.goal_manager import GoalOpportunity, GoalUnavailableReason

    blocked = GoalOpportunity(
        "private:develop_team",
        GoalKind.DEVELOP_TEAM,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
    )
    b = GoalBindingSet((m.bindings.opportunities[0], blocked), (m.bindings.bindings[0],))
    members = team(45, 40)
    result = build_post_battle_strategy_menu(
        bindings=b,
        situation=m.situation,
        battle=aftermath(),
        members=members,
        plan=build_preparation_plan(members, (ObservedOpponent("x", 1, 54),)),
        attempts=(),
        cumulative_costs=PreparationCostTotals(0, 0, 0, 0, 0),
        field_ready=True,
    )
    assert result.bindings == b


@pytest.mark.parametrize("dimension", ["attempts", "actions", "frames", "seconds", "heals"])
def test_all_cumulative_budget_dimensions_mask_training(dimension):
    members = team(45, 40)
    plan = build_preparation_plan(members, (ObservedOpponent("x", 1, 54),))
    plan = replace(plan, budget=replace(plan.budget, **{"max_" + dimension: 1}))
    costs = {"actions": 0, "frames": 0, "elapsed_seconds": 0, "heals": 0}
    if dimension != "attempts":
        costs["elapsed_seconds" if dimension == "seconds" else dimension] = 1
    attempt = PreparationAttempt("specimen-2", 40, 40, 0, **costs, failed=True)
    m = menu(members=members, plan=plan, attempts=(attempt,))
    assert m.bindings.opportunities[1].availability is GoalAvailability.UNAVAILABLE
    assert len(m.bindings.bindings) == 1
    assert (
        m.remaining_budget[["attempts", "actions", "frames", "seconds", "heals"].index(dimension)]
        == 0
    )


def test_no_progress_failure_history_is_not_erased():
    attempts = tuple(
        PreparationAttempt("specimen-2", 40, 40, 0, 1, 1, 1, failed=True) for _ in range(3)
    )
    m = menu(attempts=attempts)
    assert "no XP progress" in m.preparation_block_reason
    assert m.remaining_budget[0] == 0.75


@pytest.mark.parametrize("dimension", ["attempts", "actions", "frames", "seconds", "heals"])
def test_failed_stage_costs_without_attempt_receipt_still_exhaust_budget(dimension):
    members = team(45, 40)
    plan = build_preparation_plan(members, (ObservedOpponent("x", 1, 54),))
    costs = replace(
        PreparationCostTotals(0, 0, 0, 0, 0),
        **{
            dimension: getattr(plan.budget, "max_" + dimension),
        },
    )
    m = menu(plan=plan, costs=costs)
    assert m.bindings.opportunities[1].availability is GoalAvailability.UNAVAILABLE
    assert m.preparation_block_reason == "cumulative preparation budget exhausted"


@pytest.mark.parametrize("dimension", ["attempts", "actions", "frames", "seconds", "heals"])
def test_cumulative_costs_cannot_omit_known_receipt_costs(dimension):
    attempt = PreparationAttempt("specimen-2", 40, 41, 10, 1, 1, 1, heals=1)
    costs = replace(PreparationCostTotals(1, 1, 1, 1, 1), **{dimension: 0})
    with pytest.raises(ValueError, match="omit retained"):
        menu(attempts=(attempt,), costs=costs)


@pytest.mark.parametrize(
    "changes",
    [
        {"attempts": True},
        {"actions": -1},
        {"frames": 1.5},
        {"heals": -1},
        {"seconds": float("nan")},
        {"seconds": float("inf")},
        {"seconds": True},
    ],
)
def test_invalid_cumulative_costs_rejected(changes):
    with pytest.raises(ValueError, match="cumulative"):
        replace(PreparationCostTotals(0, 0, 0, 0, 0), **changes)


def test_unsettled_battle_cannot_offer_new_actions():
    for ready in (False, 1, None):
        with pytest.raises(ValueError, match="settled"):
            menu(ready=ready)


def test_status_on_other_member_masks_training():
    members = team(45, 40)
    members = (
        replace(
            members[0], observation=replace(members[0].observation, status=StatusCondition.POISON)
        ),
        members[1],
    )
    assert (
        menu(members=members).bindings.opportunities[1].availability is GoalAvailability.UNAVAILABLE
    )


def test_no_raw_identity_in_policy_input_and_candidate_order_equivariance():
    m, reversed_menu = menu(), menu(reverse=True)
    assert np.array_equal(m.feature_matrix(), reversed_menu.feature_matrix()[::-1])
    assert m.feature_matrix().shape[1] == len(m.feature_names())
    policy = str(m.policy_dict())
    for private in ("private:", "specimen-", "encounter", "species", "map_id", "slot"):
        assert private not in policy
    assert m.policy_dict()["schema"] == STRATEGY_SCHEMA
    encoded = json.dumps(m.policy_dict(), allow_nan=False)
    assert json.loads(encoded) == m.policy_dict()


def test_legacy_scorer_rejected_before_call():
    class Legacy:
        feature_schema_id = "pokemon.core.goal-manager.shared-candidate.v1"

        def score_features(self, _):
            pytest.fail("legacy scorer called")

    with pytest.raises(ValueError, match="separately trained"):
        menu().diagnostic_scores(Legacy())


def test_context_interactions_can_change_relative_scores_without_execution():
    m = menu()

    class SyntheticTestScorer:  # Wiring fixture, NOT a trained model.
        feature_schema_id = STRATEGY_SCHEMA
        feature_names = m.feature_names()

        def score_features(self, features):
            return features[:, self.feature_names.index("develop_team_x_recent.lost")]

    assert m.diagnostic_scores(SyntheticTestScorer()) == (0, 1)
    won = menu(
        battle=aftermath(
            result=BattleResult.WON,
            opponents_defeated=2,
            terminal_fainted_count=0,
            terminal_hp_fraction=0.5,
        )
    )
    assert won.diagnostic_scores(SyntheticTestScorer()) == (0, 0)


@pytest.mark.parametrize("scores", [[0], [0, float("nan")], [0, float("inf")], [[0], [1]]])
def test_invalid_scorer_output_rejected(scores):
    m = menu()

    class Scorer:
        feature_schema_id = STRATEGY_SCHEMA
        feature_names = m.feature_names()

        def score_features(self, _):
            return scores

    with pytest.raises(ValueError, match="scores"):
        m.diagnostic_scores(Scorer())


def test_scorer_cannot_unmask_blocked_training():
    m = menu(members=team(60, 60))

    class Scorer:
        feature_schema_id = STRATEGY_SCHEMA
        feature_names = m.feature_names()

        def score_features(self, _):
            return [0, 1e9]

    assert m.diagnostic_scores(Scorer()) == (0, None)


@pytest.mark.parametrize(
    "changes",
    [
        {"opponent_count": True},
        {"opponent_levels": (0,)},
        {"opponent_levels": [50]},
        {"opponents_defeated": 3},
        {"terminal_hp_fraction": float("nan")},
        {"last_opponent_hp_fraction": float("inf")},
        {"terminal_hp_fraction": 0.1},
        {"result": BattleResult.WON},
        {"engaged_levels": ()},
        {"result": "lost"},
    ],
)
def test_bad_aftermath_rejected(changes):
    with pytest.raises((ValueError, TypeError)):
        aftermath(**changes)


def test_zero_combat_roles_rejected_not_invented():
    members = tuple(replace(m, purpose=PreparationPurpose.COLLECTION) for m in team(45))
    with pytest.raises(ValueError, match="combat"):
        context_after_recovery(aftermath(), members)


def test_current_invalid_ratios_rejected():
    c = menu().context
    with pytest.raises(ValueError):
        replace(c, current_hp_fraction=0)
    with pytest.raises(ValueError):
        replace(c, current_pp_fraction=True)
    with pytest.raises(ValueError):
        PostBattleContext(aftermath(), (True,), 1, 0, 0, None)
