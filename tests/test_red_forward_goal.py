"""ROM-free Red observations at the prospective forward-goal boundary."""

from dataclasses import replace

import pytest
from test_red_elixir_plan import state
from test_red_goal_skills import _adapter, _Reader

from pokemon_red_completion.domain import GameState
from pokemon_red_completion.forward_goal import (
    ForwardGoalChoice,
    ForwardGoalPlan,
    ForwardGoalTerminal,
)
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.observation import SemanticStateTracker, game_mode, semantic_facts
from pokemon_red_completion.red_forward_goal import (
    RED_FORWARD_CONTEXT_NAMES,
    RED_FORWARD_EXECUTION_FLAGS,
    RedForwardGoalCollector,
    red_forward_context,
    red_forward_continuation_sha256,
    red_forward_execution_flags,
    red_forward_goal_facts,
    red_forward_verifier_sha256,
)
from pokemon_red_completion.referee import CHAMPION_DEFEATED_FACT
from pokemon_red_completion.route import HALL_OF_FAME_FACT

EXECUTION_FLAGS = (
    "routed_resource_goals",
    "quote_resource_costs",
    "completion_dose",
    "routed_recovery",
    "trainer_funding",
    "trainer_pending_recovery",
    "regional_trainer_funding",
    "remaining_acquisition_demand",
    "level_evolution_acquisitions",
)


def continuation(**kwargs):
    return red_forward_continuation_sha256(
        behavior_policy_id="frozen-stochastic-policy",
        model_sha256="a" * 64,
        source_bundle_sha256="b" * 64,
        profile_sha256="c" * 64,
        **kwargs,
    )


def test_execution_flags_have_exact_names_and_absent_equals_explicit_false():
    assert RED_FORWARD_EXECUTION_FLAGS == EXECUTION_FLAGS
    expected = {name: False for name in EXECUTION_FLAGS}
    assert red_forward_execution_flags() == expected
    assert red_forward_execution_flags({}) == expected
    assert red_forward_execution_flags(expected) == expected
    assert continuation() == continuation(execution_flags={})
    assert continuation() == continuation(execution_flags=expected)


@pytest.mark.parametrize("name", EXECUTION_FLAGS)
def test_every_execution_flag_changes_continuation_identity(name):
    assert continuation(execution_flags={name: True}) != continuation()
    assert red_forward_execution_flags({name: True})[name] is True


@pytest.mark.parametrize("name", EXECUTION_FLAGS)
@pytest.mark.parametrize("bad", [None, 0, 1, "false", "true", [], {}])
def test_present_execution_flags_cannot_use_truthy_or_missing_coercions(name, bad):
    with pytest.raises(ValueError, match="boolean"):
        red_forward_execution_flags({name: bad})
    with pytest.raises(ValueError, match="boolean"):
        continuation(execution_flags={name: bad})


@pytest.mark.parametrize("bad", [False, "metadata", [], 1])
def test_execution_flag_container_must_be_mapping(bad):
    with pytest.raises(ValueError, match="mapping"):
        red_forward_execution_flags(bad)


def test_flag_projection_is_detached_and_seed_realization_is_not_a_capability():
    metadata = {"trainer_funding": True, "seed": 17, "episode_id": "synthetic"}
    normalized = red_forward_execution_flags(metadata)
    normalized["trainer_funding"] = False
    assert metadata == {"trainer_funding": True, "seed": 17, "episode_id": "synthetic"}
    assert red_forward_execution_flags(metadata)["trainer_funding"] is True
    assert continuation(execution_flags=metadata) == continuation(
        execution_flags={"trainer_funding": True, "seed": 18},
    )


class Meter:
    def __init__(self):
        self.actions = 7
        self.frames = 70

    def checkpoint(self):
        return CompositionBudgetCheckpoint(self.actions, self.frames)

    def spend(self, actions, frames):
        self.actions += actions
        self.frames += frames


class FreshObserver:
    def observe_raw(self, raw):
        return GameState(game_mode(raw), semantic_facts(raw), "test")


def observation(raw=None, *, observer=None):
    return replace(
        _adapter(_Reader(raw=state() if raw is None else raw, ready=True)),
        semantic_observer=FreshObserver() if observer is None else observer,
        include_pp_restoration=True,
    ).observe()


def champion_raw(*, map_id=118, event=True):
    events = bytearray(319)
    if event:
        events[288] = 2  # Literal event0x901: byte288, bit1.
    return replace(state(), map_id=map_id, event_flags=bytes(events))


def declared(**changes):
    return replace(
        ForwardGoalPlan(
            "red-story-objective",
            red_forward_verifier_sha256("defeat_champion"),
            "a" * 64,
            100,
            1000,
            4,
            3,
        ),
        **changes,
    )


def choice(current, **changes):
    return replace(
        ForwardGoalChoice(
            "b" * 64,
            "c" * 64,
            "train",
            RED_FORWARD_CONTEXT_NAMES,
            red_forward_context(current),
            ("restore",),
            ((0.0,), (1.0,)),
            1,
            (0.5, 0.5),
        ),
        **changes,
    )


def harness(*, raw=None, plan=None):
    holder = [observation(raw)]
    meter = Meter()
    events = []
    collector = RedForwardGoalCollector(
        declared() if plan is None else plan,
        "defeat_champion",
        lambda: holder[0],
        meter,
        events.append,
    )
    return collector, holder, meter, events


def ready(**kwargs):
    collector, holder, meter, events = harness(**kwargs)
    collector.prepare()
    collector.anchor(choice(holder[0]))
    return collector, holder, meter, events


def test_context_uses_actual_party_hp_pp_capacity_and_owned_elixir():
    current = observation()
    context = red_forward_context(current)
    assert context[:4] == pytest.approx((282 / 389, 44 / 70, 3 / 11, 0.5))
    assert context[4:] == (
        current.situation.story_pressure,
        current.situation.team_pressure,
        current.situation.safety_pressure,
    )
    assert len(context) == len(RED_FORWARD_CONTEXT_NAMES) == 7
    assert red_forward_context(replace(current, pp_restoration=None)) == context


def test_pp_up_capacity_is_decoded_from_real_packed_slots_not_naive_base_pp():
    raw = replace(
        state(),
        party_moves=((87, 33, 0, 0), (57, 58, 45, 0)),
        party_pp=((1, 35, 0, 0), (0xC2, 0x4B, 0xF8, 0)),
    )
    assert red_forward_context(observation(raw))[1] == pytest.approx(105 / 142)


@pytest.mark.parametrize(
    "changes",
    [
        {"party_hp": None},
        {"party_max_hp": None},
        {"party_hp": (118,)},
        {"party_hp": (118, 218)},
        {"party_max_hp": (0, 217)},
        {"party_hp": (True, 164)},
        {"party_pp": None},
    ],
)
def test_malformed_current_resource_projection_refuses(changes):
    current = observation()
    with pytest.raises(ValueError):
        red_forward_context(replace(current, raw=replace(current.raw, **changes)))


def test_prepare_anchor_and_finish_are_action_free_and_before_first_input():
    collector, holder, meter, events = harness()
    before = meter.checkpoint()
    with pytest.raises(ValueError):
        collector.anchor(choice(holder[0]))
    collector.prepare()
    collector.anchor(choice(holder[0]))
    outcome = collector.finish()
    assert meter.checkpoint() == before
    assert outcome.target == (0.0, 0.0)
    assert [event["kind"] for event in events] == [
        "forward_goal_declaration",
        "forward_goal_anchor",
        "forward_goal_observation",
    ]
    with pytest.raises(ValueError):
        collector.prepare()
    with pytest.raises(ValueError):
        collector.anchor(choice(holder[0]))


@pytest.mark.parametrize("change", ["context", "names", "observation", "actions", "frames"])
def test_first_choice_must_exactly_match_prepared_resources_and_unspent_start(change):
    collector, holder, meter, events = harness()
    collector.prepare()
    anchored = choice(holder[0])
    if change == "context":
        anchored = replace(anchored, context=(0.99, *anchored.context[1:]))
    elif change == "names":
        anchored = replace(anchored, context_names=("wrong", *anchored.context_names[1:]))
    elif change == "observation":
        holder[0] = observation(replace(state(), player_money=1235))
    elif change == "actions":
        meter.spend(1, 0)
    else:
        meter.spend(0, 1)
    with pytest.raises(ValueError):
        collector.anchor(anchored)
    assert len(events) == 1


def test_champion_target_requires_both_concurrent_facts_and_hof_objective_agrees():
    assert red_forward_goal_facts("defeat_champion") == frozenset(
        {
            CHAMPION_DEFEATED_FACT,
            HALL_OF_FAME_FACT,
        }
    )
    assert red_forward_goal_facts("enter_hall_of_fame") == red_forward_goal_facts("defeat_champion")
    for raw in (champion_raw(map_id=113), champion_raw(event=False)):
        collector, holder, meter, _ = ready()
        holder[0] = observation(raw)
        meter.spend(10, 100)
        assert collector.after_macro(stop=True).target[0] == 0.0
    collector, holder, meter, _ = ready()
    holder[0] = observation(champion_raw())
    meter.spend(10, 100)
    assert collector.after_macro().target == pytest.approx((1.0, 0.06666666666666667))


def test_current_raw_completion_not_historical_tracker_latch_controls_target():
    tracker = SemanticStateTracker(replace(state(), game_started=False))
    tracker.observe(champion_raw())

    class LatchedObserver:
        def observe_raw(self, raw):
            return tracker.observe(raw)

    stale = observation(champion_raw(event=False), observer=LatchedObserver())
    assert {CHAMPION_DEFEATED_FACT, HALL_OF_FAME_FACT} <= stale.game_state.facts
    collector, holder, meter, _ = ready()
    holder[0] = stale
    meter.spend(10, 100)
    assert collector.after_macro(stop=True).target[0] == 0.0


def test_goal_already_present_initially_cannot_create_a_free_success():
    collector, _, _, events = harness(raw=champion_raw())
    with pytest.raises(ValueError):
        collector.prepare()
    assert events == []


def test_cumulative_costs_subtract_initial_meter_and_count_hp_and_pp_items():
    collector, holder, meter, events = ready()
    holder[0] = observation(replace(state(), bag_items=((53, 2), (4, 2)), bag_item_ids=(53, 4)))
    meter.spend(10, 100)
    assert collector.after_macro() is None
    holder[0] = observation(replace(state(), bag_items=((53, 1), (4, 2)), bag_item_ids=(53, 4)))
    meter.spend(20, 300)
    outcome = collector.after_macro(stop=True)
    assert outcome.counters.public_dict() == {
        "actions": 30,
        "frames": 400,
        "resources": 3,
        "macros": 2,
    }
    assert outcome.target == pytest.approx((0.0, 0.48333333333333334))
    assert len(events) == 4
    meter.spend(1, 1)
    assert collector.finish(interrupted=True) is outcome
    assert len(events) == 4  # Durable terminal is neither charged nor appended twice.


def test_finish_after_nonterminal_macro_does_not_charge_consumption_twice():
    collector, holder, meter, events = ready()
    holder[0] = observation(replace(state(), bag_items=((53, 3), (4, 2)), bag_item_ids=(53, 4)))
    meter.spend(10, 100)
    assert collector.after_macro() is None
    outcome = collector.finish()
    assert outcome.counters.resources == 1 and outcome.counters.macros == 1
    assert outcome.target == pytest.approx((0.0, 0.15))
    assert collector.finish() is outcome and len(events) == 4


def test_gross_boundary_spending_does_not_net_replenishment_against_prior_cost():
    collector, holder, meter, _ = ready(plan=declared(max_macros=4))
    holder[0] = observation(replace(state(), bag_items=((53, 3), (4, 2)), bag_item_ids=(53, 4)))
    meter.spend(1, 1)
    collector.after_macro()
    holder[0] = observation(state())  # Explicit boundary gain, no negative refund.
    meter.spend(1, 1)
    collector.after_macro()
    holder[0] = observation(replace(state(), bag_items=((53, 3), (4, 2)), bag_item_ids=(53, 4)))
    meter.spend(1, 1)
    outcome = collector.after_macro(stop=True)
    assert outcome.counters.resources == 2


@pytest.mark.parametrize(
    "actions,frames,resources,macros,consume",
    [
        (101, 10, 4, 3, False),
        (10, 1001, 4, 3, False),
        (10, 10, 4, 1, False),
        (10, 10, 0, 3, True),
    ],
)
def test_declared_action_frame_macro_and_resource_budgets_control_success(
    actions,
    frames,
    resources,
    macros,
    consume,
):
    collector, holder, meter, _ = ready(plan=declared(max_macros=macros, max_resources=resources))
    if macros == 1:
        meter.spend(1, 1)
        assert collector.after_macro().target[0] == 0.0
        return
    raw = champion_raw()
    if consume:
        raw = replace(raw, bag_items=((53, 3), (4, 2)), bag_item_ids=(53, 4))
    holder[0] = observation(raw)
    meter.spend(actions, frames)
    outcome = collector.after_macro()
    assert outcome.observed_goal is True and outcome.target[0] == 0.0


def test_nonconsumable_inventory_change_is_not_a_consumed_resource_unit():
    raw = replace(
        state(), bag_items=(*state().bag_items, (6, 1)), bag_item_ids=(*state().bag_item_ids, 6)
    )
    collector, holder, meter, _ = ready(raw=raw)
    holder[0] = observation(state())
    meter.spend(10, 100)
    outcome = collector.after_macro(stop=True)
    assert outcome.counters.resources == 0
    assert outcome.target == pytest.approx((0.0, 0.06666666666666667))


@pytest.mark.parametrize("events", [None, bytes(318), bytes(320), [0] * 319])
def test_unknown_current_event_bytes_are_not_a_fabricated_failed_goal(events):
    collector, holder, meter, recorded = ready()
    holder[0] = replace(holder[0], raw=replace(holder[0].raw, event_flags=events))
    meter.spend(10, 100)
    with pytest.raises(ValueError):
        collector.after_macro(stop=True)
    assert len(recorded) == 2 and collector.outcome is None
    assert collector.finish(interrupted=True).target is None


def test_interruption_retains_fresh_meter_prefix_without_inspecting_unknown_state():
    collector, holder, meter, events = ready()
    meter.spend(10, 100)
    collector.after_macro()
    meter.spend(5, 70)

    def unreadable():
        raise AssertionError("interruption must not claim a fresh observation")

    collector.observe = unreadable
    outcome = collector.finish(interrupted=True)
    assert outcome.terminal is ForwardGoalTerminal.INTERRUPTED
    assert outcome.target is None and outcome.observed_goal is None
    assert outcome.counters.public_dict() == {
        "actions": 15,
        "frames": 170,
        "resources": 0,
        "macros": 1,
    }
    assert events[-1]["outcome"]["target"] is None


@pytest.mark.parametrize("hook", ["prepare", "anchor", "after_macro", "finish"])
def test_observation_hook_cannot_silently_spend_controller_input(hook):
    collector, holder, meter, events = harness()
    if hook != "prepare":
        collector.prepare()
    if hook in {"after_macro", "finish"}:
        collector.anchor(choice(holder[0]))
    prior = len(events)

    def acting_observation():
        meter.spend(1, 1)
        return holder[0]

    collector.observe = acting_observation
    with pytest.raises(ValueError, match="actions"):
        if hook == "anchor":
            collector.anchor(choice(holder[0]))
        else:
            getattr(collector, hook)()
    assert len(events) == prior and collector.outcome is None


@pytest.mark.parametrize(
    "failed_kind",
    [
        "forward_goal_declaration",
        "forward_goal_anchor",
        "forward_goal_observation",
    ],
)
def test_append_that_acts_poisoned_even_if_event_was_already_stored(failed_kind):
    collector, holder, meter, events = harness()

    def acting_append(event):
        events.append(event)
        if event["kind"] == failed_kind:
            meter.spend(1, 1)

    collector.append = acting_append
    with pytest.raises(ValueError, match="recording attempted"):
        collector.prepare()
        collector.anchor(choice(holder[0]))
        collector.after_macro(stop=True)
    count = len(events)
    assert collector.outcome is None
    with pytest.raises(ValueError):
        collector.finish(interrupted=True)
    assert len(events) == count


@pytest.mark.parametrize("bag", [None, ((82, 1), (82, 2)), ((82, 0),), ((82, True),)])
def test_invalid_post_macro_bag_never_creates_a_target(bag):
    collector, holder, meter, events = ready()
    holder[0] = replace(holder[0], raw=replace(holder[0].raw, bag_items=bag))
    meter.spend(10, 100)
    with pytest.raises(ValueError):
        collector.after_macro(stop=True)
    assert len(events) == 2 and collector.outcome is None
    assert collector.finish(interrupted=True).target is None
