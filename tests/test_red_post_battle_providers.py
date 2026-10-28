from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_post_battle_strategy import aftermath
from test_red_party_preparation import setup as party_setup

from pokemon_red_completion import red_post_battle_providers as p
from pokemon_red_completion.executor import (
    CountingExecutor,
    MonotonicWallTimeBudgetController,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind, GoalSituation
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer


@pytest.fixture
def rig(monkeypatch, tmp_path):
    members, plan = party_setup()
    raw = NS(map_id=9, battle_state=0, player_money=100, bag_items=())
    state = NS(
        raw=raw,
        members=members,
        facts=frozenset(),
        boxes=("box",),
        owned=frozenset({"old"}),
        fail=None,
        claim=True,
        claims=[],
        retained=[],
        logs={},
        story_calls=0,
        wild_calls=0,
        steps=1,
        clock=0,
        auth_bad=False,
        restored=True,
        log_failure=False,
    )

    class Emulator:
        frame_count = 0
        pressed_buttons = ()

        def tick(self, frames):
            self.frame_count += frames

    em = Emulator()
    ctrl = WindowedFrameBudgetController(
        MonotonicWallTimeBudgetController(
            em, maximum_wall_seconds=60, monotonic_clock=lambda: state.clock
        ),
        maximum_frames_per_window=300000,
        maximum_total_frames=300000,
    )
    actions = CountingExecutor(NS(execute=lambda _: ctrl.tick(1)))

    def observe():
        return NS(
            raw=state.raw,
            input_ready=True,
            game_state=state.facts,
            collection_observation=NS(owned_species=state.owned),
            situation=GoalSituation(0.2, 0.4, 0.3, 0.1, 0, 0, 0, 0, 0.2),
        )

    adapter = NS(observe=observe, graph=NS(completed_ids=lambda facts: facts))
    reader = NS(read_all_box_states=lambda: state.boxes)
    runtime = NS(emulator=ctrl, reader=reader, adapter=adapter, observer=NS())
    story_battler = p.FrozenTrainerBattler(
        ctrl, None, tmp_path / "story", "a" * 40, "root", "b" * 64, {}
    )
    actor = object.__new__(p.FrozenLoreleiStoryController)
    actor.battler, actor.contract, actor.admission, actor.maximum_decisions = (
        story_battler,
        None,
        b"test",
        80,
    )
    actor.last_completion = None
    monkeypatch.setattr(p.FrozenLoreleiStoryController, "require_objective", lambda *a, **k: None)
    runtime.league_story_battle_controller = actor
    skill = p.RedCartridgeLoreleiSkill(runtime, actions, None)
    wild = p.FrozenTrainerBattler(
        ctrl,
        NS(to_dict=lambda: {"weight": 1}),
        tmp_path / "wild",
        "a" * 40,
        "root",
        "b" * 64,
        {},
        model_sha256=p.FROZEN_K_SHA256,
        qualification_sha256=p.K_QUALIFICATION_SHA256,
    )

    def play_actions(port):
        for _ in range(state.steps):
            port.execute(None)

    def story_execute():
        state.story_calls += 1
        play_actions(skill.actions)
        if state.fail == "lost":
            actor.last_completion = NS(outcome="lost", field_ready=True)
            raise p.LoreleiStoryBattleStopped("retained loss")
        if state.fail == "unsettled":
            actor.last_completion = NS(outcome="lost", field_ready=False)
            raise p.LoreleiStoryBattleStopped("unsettled")
        if state.fail == "crash":
            raise RuntimeError("native execution error")
        if state.fail == "interrupt":
            raise KeyboardInterrupt()
        state.facts = frozenset({"story"})
        return GoalExecutionReport(state.steps, state.steps, {})

    binding = ExecutableGoalBinding(
        "story",
        GoalKind.ADVANCE_STORY,
        0.6,
        0.3,
        story_execute,
        lambda _: (
            GoalVerification.succeeded()
            if "story" in state.facts
            else GoalVerification.failed(p.GoalFailureReason.OUTCOME_NOT_VERIFIED)
        ),
    )
    monkeypatch.setattr(
        p,
        "RedStoryGoalBindingProvider",
        lambda *a: NS(offer=lambda _: RedGoalBindingOffer.available(binding)),
    )
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: state.restored)
    monkeypatch.setattr(p, "observe_preparation_members", lambda *a: state.members)
    monkeypatch.setattr(
        p, "quote_preparation_route", lambda *a: p.PreparationRouteQuote("corridor", 12, 15, 174)
    )
    monkeypatch.setattr(
        p.RedTrainerEvolutionGuard, "from_rom", lambda *a: NS(level_edges=frozenset())
    )

    def wild_execute(**kwargs):
        state.wild_calls += 1
        assert kwargs["recovery_home_map"] == 174 and kwargs["maximum_battles"] == 8
        play_actions(kwargs["actions"])
        if state.fail == "crash":
            raise RuntimeError("wild error")
        first, trainee, third = state.members
        if state.fail != "no_xp":
            trainee = replace(trainee, observation=replace(trainee.observation, experience=1200))
        state.members = (first, trainee, third)
        state.raw = NS(**(vars(state.raw) | {"map_id": 174}))
        return {"status": "complete", "xp_gained": 99999}  # Verifier must ignore this assertion.

    monkeypatch.setattr(p, "execute_wild_preparation", wild_execute)

    def auth():
        if state.auth_bad:
            raise ValueError("source authentication failed")

    def claim(kind):
        state.claims.append(kind)
        return state.claim

    def record(name, value):
        if state.log_failure:
            raise OSError("log unavailable")
        state.logs[name] = value

    providers = p.RedPostBattleProviders(
        runtime=runtime,
        actions=actions,
        story_skill=skill,
        wild_battler=wild,
        route=NS(rom=b"rom"),
        source_id="wild:example",
        recovery_home_map=174,
        plan=plan,
        attempts=(),
        cumulative_costs=p.PreparationCostTotals(0, 0, 0, 0, 0),
        battle=aftermath(),
        authenticate=auth,
        claim=claim,
        retain=lambda *args: state.retained.append(args),
        record=record,
    )
    state.provider, state.actions, state.ctrl, state.em = providers, actions, ctrl, em
    return state


def select(rig, kind):
    menu = rig.provider.quote()
    return next(b for b in menu.bindings.bindings if b.kind is kind)


def test_quote_is_action_free_and_has_real_separate_dispatch(rig):
    menu = rig.provider.quote()
    assert {b.kind for b in menu.bindings.bindings} == {
        GoalKind.DEVELOP_TEAM,
        GoalKind.ADVANCE_STORY,
    }
    assert not rig.claims and not rig.retained and rig.em.frame_count == 0
    with pytest.raises(ValueError, match="already bound"):
        rig.provider.quote()


@pytest.mark.parametrize("kind", [GoalKind.DEVELOP_TEAM, GoalKind.ADVANCE_STORY])
def test_one_selected_skill_only_and_both_alternatives_consumed(rig, kind):
    binding = select(rig, kind)
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert rig.claims == [kind] and len(rig.retained) == 1
    assert rig.story_calls + rig.wild_calls == 1
    assert rig.logs["post-battle-cost"]["actions"] == 1
    assert rig.logs["post-battle-cost"]["frames"] == 1
    for other in rig.provider._menu.bindings.bindings:
        with pytest.raises(ValueError, match="consumed"):
            other.execute()
    with pytest.raises(ValueError, match="exact executed"):
        binding.verify(GoalExecutionReport(1, 1, {}))


@pytest.mark.parametrize("fault", ["stale", "authentication", "claim", "config", "weights"])
def test_changed_source_failed_claim_or_configuration_prevents_inputs(rig, fault):
    binding = select(rig, GoalKind.DEVELOP_TEAM)
    if fault == "stale":
        rig.raw = NS(**(vars(rig.raw) | {"player_money": 90}))
    elif fault == "authentication":
        rig.auth_bad = True
    elif fault == "claim":
        rig.claim = False
    elif fault == "weights":
        rig.provider.wild_battler.model = NS(to_dict=lambda: {"weight": 2})
    else:
        rig.provider.limits = replace(rig.provider.limits, actions=6000)
    with pytest.raises(ValueError):
        binding.execute()
    assert rig.em.frame_count == rig.actions.actions_executed == 0
    assert rig.story_calls == rig.wild_calls == 0


@pytest.mark.parametrize("kind", [GoalKind.DEVELOP_TEAM, GoalKind.ADVANCE_STORY])
def test_errors_preserve_terminal_and_propagate_no_fallback(rig, kind):
    binding = select(rig, kind)
    rig.fail = "crash"
    with pytest.raises(RuntimeError):
        binding.execute()
    assert len(rig.retained) == 1 and isinstance(rig.retained[0][2], RuntimeError)
    assert rig.story_calls + rig.wild_calls == 1
    assert rig.logs["post-battle-cost"]["actions"] == 1


def test_settled_loss_is_failed_outcome_not_execution_crash(rig):
    binding = select(rig, GoalKind.ADVANCE_STORY)
    rig.fail = "lost"
    report = binding.execute()
    assert report.evidence["status"] == "lost"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    assert rig.retained[0][2] is None


@pytest.mark.parametrize(
    "fault,exception",
    [("unsettled", p.LoreleiStoryBattleStopped), ("interrupt", KeyboardInterrupt)],
)
def test_unsettled_and_interruption_are_not_normalized(rig, fault, exception):
    binding = select(rig, GoalKind.ADVANCE_STORY)
    rig.fail = fault
    with pytest.raises(exception):
        binding.execute()
    assert isinstance(rig.retained[0][2], exception)


@pytest.mark.parametrize("dimension", ["actions", "frames", "seconds"])
def test_hard_limits_stop_before_excess_inputs_and_retain(rig, dimension):
    rig.provider.limits = p.PostBattlePacketLimits(actions=1, frames=1, seconds=60)
    binding = select(rig, GoalKind.DEVELOP_TEAM)
    if dimension == "seconds":
        rig.clock = 61
    elif dimension == "frames":
        rig.provider.actions.delegate.execute = lambda _: rig.ctrl.tick(2)
    else:
        rig.steps = 2
    with pytest.raises(RuntimeError):
        binding.execute()
    assert rig.em.frame_count <= 1 and rig.actions.actions_executed <= 1
    assert len(rig.retained) == 1


def test_terminal_retained_even_if_cost_log_fails(rig):
    binding = select(rig, GoalKind.DEVELOP_TEAM)
    rig.log_failure = True
    with pytest.raises(OSError):
        binding.execute()
    assert len(rig.retained) == 1


@pytest.mark.parametrize(
    "fault", ["no_xp", "cash", "bag", "boxes", "dex", "health", "story", "species"]
)
def test_verifier_reads_actual_outcome_not_self_reported_success(rig, fault):
    binding = select(rig, GoalKind.DEVELOP_TEAM)
    rig.fail = fault
    report = binding.execute()
    if fault == "cash":
        rig.raw = NS(**(vars(rig.raw) | {"player_money": 99}))
    elif fault == "bag":
        rig.raw = NS(**(vars(rig.raw) | {"bag_items": ((1, 1),)}))
    elif fault == "boxes":
        rig.boxes = ()
    elif fault == "dex":
        rig.owned = frozenset()
    elif fault == "health":
        rig.restored = False
    elif fault == "story":
        rig.facts = frozenset({"unexpected"})
    elif fault == "species":
        first, *others = rig.members
        rig.members = (
            replace(first, observation=replace(first.observation, species_id=99)),
            *others,
        )
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("dimension", ["attempts", "actions", "frames", "seconds", "heals"])
def test_outer_budget_masks_training_without_promoting_or_blocking_story(rig, dimension):
    rig.provider.costs = replace(
        rig.provider.costs, **{dimension: getattr(rig.provider.plan.budget, "max_" + dimension)}
    )
    menu = rig.provider.quote()
    assert [b.kind for b in menu.bindings.bindings] == [GoalKind.ADVANCE_STORY]


def test_missing_round_trip_masks_training(rig, monkeypatch):
    def missing(*args):
        raise ValueError("no recovery route")

    monkeypatch.setattr(p, "quote_preparation_route", missing)
    menu = rig.provider.quote()
    assert [b.kind for b in menu.bindings.bindings] == [GoalKind.ADVANCE_STORY]
    assert rig.provider.preparation_reason == "no recovery route"


def test_unavailable_story_does_not_suppress_valid_training(rig, monkeypatch):
    monkeypatch.setattr(
        p,
        "RedStoryGoalBindingProvider",
        lambda *a: NS(
            offer=lambda _: RedGoalBindingOffer.unavailable(
                GoalKind.ADVANCE_STORY, p.GoalUnavailableReason.MISSING_CAPABILITY
            )
        ),
    )
    menu = rig.provider.quote()
    assert [b.kind for b in menu.bindings.bindings] == [GoalKind.DEVELOP_TEAM]


def test_no_available_goals_refuses_before_scoring_or_claim(rig, monkeypatch):
    monkeypatch.setattr(
        p,
        "RedStoryGoalBindingProvider",
        lambda *a: NS(
            offer=lambda _: RedGoalBindingOffer.unavailable(
                GoalKind.ADVANCE_STORY, p.GoalUnavailableReason.MISSING_CAPABILITY
            )
        ),
    )
    rig.provider.costs = replace(rig.provider.costs, attempts=rig.provider.plan.budget.max_attempts)
    with pytest.raises(ValueError, match="no executable"):
        rig.provider.quote()
    assert not rig.claims and rig.em.frame_count == 0


def test_quote_rejects_input_side_effects(rig, monkeypatch):
    def bad_quote(*args):
        rig.ctrl.tick(1)
        return p.PreparationRouteQuote("corridor", 12, 15, 174)

    monkeypatch.setattr(p, "quote_preparation_route", bad_quote)
    with pytest.raises(ValueError, match="source changed"):
        rig.provider.quote()
    assert not rig.claims


def test_projected_return_context_follows_actual_warps_not_original_outside():
    from pokemon_red_completion.global_router import MacroEdge
    from pokemon_red_completion.route_executor import TraversalSnapshot

    start = TraversalSnapshot(9, (6, 9), True, mode="land", last_outside_map=1)
    graph = NS(outside_nodes={9, 34}, retained_outside_overrides={})
    plan = NS(
        macro_path=NS(
            edges=(
                MacroEdge(34),
                MacroEdge(194, kind="warp"),
                MacroEdge(198, kind="warp"),
                MacroEdge(194, kind="warp"),
            )
        ),
        terminal_map=194,
        terminal_at=(13, 25),
        terminal_mode="land",
    )
    final = p.projected_route_terminal(graph, start, plan)
    assert final.last_outside_map == 34 and final.map_id == 194
    assert final.at == (13, 25) and final.ready


def test_unresolved_return_context_is_not_invented():
    from pokemon_red_completion.global_router import MacroEdge
    from pokemon_red_completion.route_executor import TraversalSnapshot

    start = TraversalSnapshot(194, (1, 1), True, last_outside_map=None)
    plan = NS(macro_path=NS(edges=(MacroEdge(None, kind="return"),)))
    with pytest.raises(p.RoutePlanningError, match="unresolved"):
        p.projected_route_terminal(NS(), start, plan)


@pytest.mark.parametrize(
    "values", [{"actions": True}, {"frames": 0}, {"seconds": 181}, {"wild_battles": 9}]
)
def test_packet_limits_strict(values):
    with pytest.raises(ValueError):
        p.PostBattlePacketLimits(**values)
