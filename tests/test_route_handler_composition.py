"""Behavioral contracts through production handler construction and wrappers."""
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import pytest

from test_gen1_route_runtime import FakeReader
from test_red_routed_recovery import make_test_raw
from test_red_training_ground_route import _world
from test_red_travel_capture import Harness
from test_red_collection_fly import scene
from pokemon_red_completion import red_training_ground_route as ground
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_route_runtime import Gen1RouteInterruptionHandler
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.route_executor import (
    TraversalSnapshot, RouteExecutionError,
)
from pokemon_red_completion.goal_manager import GoalKind, GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding, GoalExecutionReport, GoalVerification,
)
from pokemon_red_completion.red_player_engaged_story import EngagedStoryRouteHandler
from pokemon_red_completion.red_safari_exit import (
    RedSafariExitDialogueHandler, RedSafariDepartureInterruptionHandler,
)


def walking_plan(map_id, points):
    return RoutePlan(MacroPath((map_id,), ()), points[0], "land", (),
        LocalPath(tuple(points), tuple(LocalEdge(p, "right") for p in points[1:]),
                  ("land",) * len(points)), points[-1], "land")


@pytest.mark.parametrize("dialogues", [0, 2])
@pytest.mark.parametrize("fault", [None, "unverified", "unpoisoned", "unknown_dialogue"])
def test_ground_real_assembly_keeps_poison_boundary_and_learned_owner(monkeypatch, dialogues, fault):
    reader = FakeReader(make_test_raw(map_id=25, x=1, y=1, hp=(30, 30)))
    reader.read_all_box_states = lambda: ()
    reader.read_pokedex_state = lambda: ()
    events = []
    class Port:
        def execute(self, action):
            events.append(action.kind)
            if action.kind is MacroActionKind.MOVE:
                reader.raw = replace(reader.raw, player_x=reader.raw.player_x + 1)
                if reader.raw.player_x == 2:
                    reader.raw = replace(reader.raw, battle_state=2)
                elif reader.raw.player_x == 3:
                    reader.dialogue_visible = True
                    if fault != "unknown_dialogue":
                        reader.raw = replace(reader.raw, party_hp=(0, 30), party_status=(0, 0))
            if action.kind is MacroActionKind.CANCEL:
                reader.dialogue_visible = False
            return action
    port = Port()
    learned = []
    def factory():
        if not reader.raw.battle_state:
            return None
        def play():
            learned.append("learned")
            reader.raw = replace(reader.raw, battle_state=0, party_hp=(3, 30),
                                 party_status=(0 if fault == "unpoisoned" else 8, 0))
            return GoalExecutionReport(1, 1, {"battle": {"outcome": "won"}})
        return ExecutableGoalBinding("pokemon.red:retained-engagement:exact", GoalKind.RECOVER_CONTROL,
            .1, .1, play, lambda _: GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if fault == "unverified" else GoalVerification.succeeded())
    monkeypatch.setattr(ground, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(ground, "ground_route_capability_projector", lambda *a: None)
    monkeypatch.setattr(ground, "Gen1FieldMovePort", lambda actions, *a, **k: actions)
    world = _world()
    monkeypatch.setattr(type(world), "plan_feasible_to_map",
        lambda *a, **k: walking_plan(25, ((1, 1), (1, 2), (1, 3))))
    monkeypatch.setattr(type(world), "replanner", lambda _: lambda request:
        walking_plan(25, (request.current.at, (1, 3))))
    transition = ground.RedVermilionGroundTransition(b"rom", world,
        destination_map=25, destination_at=(1, 3), allow_wild_faints=True,
        allow_field_faint_dialogue=True, maximum_scripted_dialogues=dialogues,
        trainer_binding_factory=factory)
    succeeds = fault is None or fault == "unknown_dialogue" and dialogues > 0
    if succeeds:
        transition(port, reader, SimpleNamespace(pressed_buttons=()))
        assert (reader.raw.player_y, reader.raw.player_x) == (1, 3)
        assert not reader.dialogue_visible
        assert events.count(MacroActionKind.CANCEL) == 1
        assert reader.raw.party_hp == ((3, 30) if fault else (0, 30))
    else:
        with pytest.raises(RouteExecutionError):
            transition(port, reader, SimpleNamespace(pressed_buttons=()))
        assert MacroActionKind.CANCEL not in events
    assert learned == ["learned"]


def test_zero_trainer_handler_does_not_advertise_sight_authority():
    reader = FakeReader(make_test_raw())
    base = Gen1RouteInterruptionHandler(SimpleNamespace(), reader, 1, 0, 120)
    assert "trainer_sight" not in base.handled_hazard_kinds
    assert "battle:2" not in base.handled_interruption_kinds
    learned = EngagedStoryRouteHandler(base, reader, lambda: None)
    assert "trainer_sight" in learned.handled_hazard_kinds
    assert {"trainer_engagement", "battle:2"} <= learned.handled_interruption_kinds
    with pytest.raises(RouteExecutionError, match="exact learned engagement"):
        learned.handle(TraversalSnapshot(reader.raw.map_id, (reader.raw.player_y, reader.raw.player_x),
                                        False, "battle:2"))


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("learned", [False, True])
def test_verified_capture_refreshes_or_hands_off_pending_trainer(pending, learned):
    harness = Harness()
    refreshed = []
    harness.handler.fallback.observe_native_field_boundary = lambda: refreshed.append(harness.raw)
    harness.trainer_engagement_active = lambda: pending and harness.calls > 0
    owner = EngagedStoryRouteHandler(harness.handler, harness, lambda: None)
    receipt = (owner if learned else harness.handler).handle(harness.start)
    assert receipt.details["verified"] is True
    assert receipt.details.get("pending_interruption_kind") == ("trainer_engagement" if pending else None)
    assert len(refreshed) == int(not pending)
    assert harness.calls == 1 and not harness.fallback_calls


def test_safari_wrappers_forward_verified_boundary_without_controller_input():
    from pokemon_red_completion.route_executor import observe_native_field_boundary
    seen = []
    leaf = SimpleNamespace(observe_native_field_boundary=lambda: seen.append("leaf"))
    inner = RedSafariExitDialogueHandler(object(), object(), leaf)
    outer = RedSafariDepartureInterruptionHandler(object(), object(), object(), inner)
    observe_native_field_boundary(outer)
    assert seen == ["leaf"]


@pytest.mark.parametrize("pending_trainers", [1, 2])
def test_fly_real_assembly_refreshes_after_trainer_before_poison_faint(scene, monkeypatch, pending_trainers):
    game = scene.game
    original_execute = game.execute
    original_readiness = game.read_input_readiness
    from pokemon_red_completion.observation import InputReadiness
    monkeypatch.setattr(game, "read_input_readiness", lambda: InputReadiness(
        joy_ignore=0 if game.stage == "dialogue" or original_readiness().ready else 1,
        simulated_joypad_index=0, npc_movement_script_table=0,
        player_moving_direction=4 if game.stage == "dialogue" else 0, status_flags_5=0))
    game.raw = replace(game.raw, party_hp=(30, 30, 30), party_status=(0, 0, 0))
    monkeypatch.setattr(game, "save_state_bytes", lambda: repr(game.raw).encode(), raising=False)
    monkeypatch.setattr(game, "read_all_box_states", lambda: (), raising=False)
    monkeypatch.setattr(game, "read_pokedex_state", lambda: (), raising=False)
    monkeypatch.setattr(game, "pressed_buttons", (), raising=False)
    step = [0]
    wins = []
    pending = [False]
    monkeypatch.setattr(game, "trainer_engagement_active", lambda: pending[0])
    # A real two-step onward walk; Fly menu behavior stays the existing fixture.
    plan = walking_plan(5, ((6, 9), (6, 10), (6, 11)))
    scene.router.world.plan_feasible_to_map = lambda *a, **k: plan
    def execute(action):
        if action.kind is MacroActionKind.MOVE and game.stage == "landed":
            game.actions.append(action);game.frame_count += action.repeat;step[0] += 1
            game.raw = replace(game.raw, player_x=9 + step[0])
            if step[0] == 1:
                game.raw = replace(game.raw, battle_state=2)
            else:
                game.raw = replace(game.raw, party_hp=(0, 30, 30), party_status=(0, 0, 0))
                game.stage = "dialogue"
        else:
            original_execute(action)
    monkeypatch.setattr(game, "execute", execute)
    scene.observer.observe = lambda: TraversalSnapshot(game.raw.map_id,
        (game.raw.player_y, game.raw.player_x), game.read_input_readiness().ready and not game.raw.battle_state,
        "battle:2" if game.raw.battle_state else "trainer_engagement" if pending[0]
        else "scripted_dialogue" if game.stage == "dialogue" else None, mode="land")
    def factory():
        if not game.raw.battle_state and not pending[0]:
            return None
        def play():
            wins.append("learned")
            scene.router.actions.execute(MacroAction(MacroActionKind.WAIT))
            game.raw = replace(game.raw, battle_state=0, party_hp=(3, 30, 30), party_status=(8, 0, 0))
            pending[0] = len(wins) < pending_trainers
            return GoalExecutionReport(1, 1, {"battle": {"outcome": "won", "money_delta": 0}})
        return ExecutableGoalBinding("pokemon.red:retained-engagement:exact", GoalKind.RECOVER_CONTROL,
                                     .1, .1, play, lambda _: GoalVerification.succeeded())
    def wrap(inner, spec):
        inner.inner.move_slot_policy = lambda _: pytest.fail("legacy trainer combat")
        return EngagedStoryRouteHandler(inner, game, factory)
    scene.router.interruption_handler_wrapper = wrap
    binding = scene.bind()
    assert binding is not None
    report = binding.execute()
    assert binding.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED
    assert wins == ["learned"] * pending_trainers
    assert not scene.provider_calls and not report.evidence["destination_executed"]
    assert game.raw.party_hp == (0, 30, 30)
    assert game.dialogue_cancels == 1 and step[0] == 2


@pytest.mark.parametrize("landing", ["replacement", "removed", "unrelated"])
def test_ground_replan_replaces_active_faint_warps(monkeypatch, landing):
    reader = FakeReader(make_test_raw(map_id=25, x=1, y=1, hp=(3, 30), status=(8, 0)))
    reader.read_all_box_states = lambda: ()
    reader.read_pokedex_state = lambda: ()
    landings = {"replacement": (31, (2, 2)), "removed": (30, (3, 3)), "unrelated": (32, (4, 4))}
    calls, receipts = [], []
    class Port:
        def execute(self, action):
            if action.kind is MacroActionKind.CANCEL:
                target, (y, x) = landings[landing]
                reader.raw = replace(reader.raw, map_id=target, player_y=y, player_x=x)
                reader.dialogue_visible = False
    port = Port()
    def fake_plan(target, at):
        return SimpleNamespace(segments=(SimpleNamespace(passage_kind="warp", source_map=25,
            target_map=target, transition=SimpleNamespace(exit_at=(1, 1), arrival_at=at)),))
    initial = fake_plan(30, (3, 3)); replacement = fake_plan(31, (2, 2))
    world = _world()
    monkeypatch.setattr(ground, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(ground, "ground_route_capability_projector", lambda *a: None)
    monkeypatch.setattr(ground, "Gen1FieldMovePort", lambda actions, *a, **k: actions)
    monkeypatch.setattr(type(world), "plan_feasible_to_map", lambda *a, **k: initial)
    def replan(request):
        calls.append(request)
        return replacement
    monkeypatch.setattr(type(world), "replanner", lambda _: replan)
    def execute(plan, *args, interruption_handler, replanner, **kwargs):
        assert plan is initial and replanner("observed blocker") is replacement
        reader.raw = replace(reader.raw, party_hp=(0, 30), party_status=(0, 0))
        reader.dialogue_visible = True
        receipts.append(interruption_handler.handle(TraversalSnapshot(25, (1, 1), False, "scripted_dialogue")))
    monkeypatch.setattr(ground, "execute_route", execute)
    transition = ground.RedVermilionGroundTransition(b"rom", world, destination_map=31,
        destination_at=(2, 2), allow_wild_faints=True, allow_field_faint_dialogue=True,
        maximum_scripted_dialogues=2, trainer_binding_factory=lambda: None)
    if landing == "replacement":
        transition(port, reader, SimpleNamespace(pressed_buttons=()))
        assert receipts[0].details["declared_native_warp"] is True
    else:
        with pytest.raises(RouteExecutionError, match="protected resources"):
            transition(port, reader, SimpleNamespace(pressed_buttons=()))
        assert not receipts
    assert calls == ["observed blocker"]
    assert reader.raw.party_hp == (0, 30) and reader.raw.player_money == 209


@pytest.mark.parametrize("learned", [False, True])
def test_ground_combined_handler_retains_whole_party_escape(monkeypatch, learned):
    from pokemon_red_completion import gen1_route_runtime, wild_party_flee
    from pokemon_red_completion.route_1_wild import Route1WildFleeEvidence
    reader = FakeReader(make_test_raw(map_id=25, x=1, y=1, hp=(0, 30)))
    seen, receipts = [], []
    port = SimpleNamespace(execute=lambda _: None)
    emulator = SimpleNamespace(pressed_buttons=())
    def escape(actions, observed, encounter, **options):
        assert actions is port and observed is reader and options["emulator"] is emulator
        assert options["allow_new_faints"] and options["allow_status_changes"]
        assert encounter.battle_state == 1 and encounter.party_hp == (0, 30)
        seen.append("whole-party")
        reader.raw = replace(reader.raw, battle_state=0)
        return SimpleNamespace(verified=True, map_id=25, player_y=1, player_x=1,
                               public_dict=lambda: {"verified": True})
    monkeypatch.setattr(wild_party_flee, "flee_with_fainted_lead", escape)
    monkeypatch.setattr(gen1_route_runtime, "flee_wild", lambda *a, **k: pytest.fail("legacy escape"))
    monkeypatch.setattr(ground, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(ground, "ground_route_capability_projector", lambda *a: None)
    monkeypatch.setattr(ground, "Gen1FieldMovePort", lambda actions, *a, **k: actions)
    world = _world()
    monkeypatch.setattr(type(world), "plan_feasible_to_map", lambda *a, **k: object())
    monkeypatch.setattr(type(world), "replanner", lambda _: None)
    def execute(plan, *args, interruption_handler, **kwargs):
        reader.raw = replace(reader.raw, battle_state=1)
        receipts.append(interruption_handler.handle(TraversalSnapshot(25, (1, 1), False, "wild_battle")))
    monkeypatch.setattr(ground, "execute_route", execute)
    factory = (lambda: pytest.fail("wild encounter reached trainer factory")) if learned else None
    ground.RedVermilionGroundTransition(b"rom", world, destination_map=25, destination_at=(1, 1),
        allow_wild_faints=True, maximum_scripted_dialogues=2, trainer_binding_factory=factory)(port, reader, emulator)
    assert seen == ["whole-party"] and len(receipts) == 1
    assert receipts[0].details["verified"] is True and reader.raw.party_hp == (0, 30)


@pytest.mark.parametrize("failed", [False, True])
def test_capture_party_pc_access_keeps_supplied_trainer_owner(monkeypatch, failed):
    from test_red_routed_capture_support import fixture
    from pokemon_red_completion import red_routed_capture_support as support
    router, bindings, observation, calls = fixture(monkeypatch)
    wrapped = []
    original_travel = support.execute_route
    handler = SimpleNamespace(handle=lambda snapshot: (_ for _ in ()).throw(
        RouteExecutionError("retained trainer stop")) if failed else calls.append("learned"))
    def wrap(inner, spec):
        assert spec is router.runtime.profile.providers[0]
        wrapped.append(inner)
        return handler
    router.interruption_handler_wrapper = wrap
    def travel(*args, interruption_handler, **kwargs):
        assert interruption_handler is handler
        interruption_handler.handle(None)
        return original_travel(*args, **kwargs)
    monkeypatch.setattr(support, "execute_route", travel)
    binding = support.bind_capture_party_support(router, bindings, observation).bindings[0]
    assert not calls and not wrapped
    if failed:
        with pytest.raises(RouteExecutionError, match="retained trainer stop"):
            binding.execute()
        assert not calls
    else:
        report = binding.execute()
        assert binding.verify(report).status.value == "succeeded"
        assert report.actions_executed == 15 and report.frames_executed == 100
        assert calls[:2] == ["learned", "travel"]
    assert len(wrapped) == 1


from test_red_resource_goal_router import fixture as resource_fixture


@pytest.mark.parametrize("fault", [None, "unverified_income", "withdrawal_cash", "trainer_stop"])
def test_capture_item_pc_access_preserves_owner_and_verified_cash(resource_fixture, monkeypatch, fault):
    from test_red_resource_goal_router import _AreaExecutor
    from pokemon_red_completion import red_routed_capture_items as items
    from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider
    from pokemon_red_completion.observation import ItemId, MapId
    from pokemon_red_completion.red_routed_semantic_goal import FreshRedGoalObservation
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    f = resource_fixture
    f.reader.raw = replace(f.reader.raw, map_id=int(MapId.ROUTE_1), player_money=500,
        bag_items=((int(ItemId.POKE_BALL), 10),), bag_item_ids=(int(ItemId.POKE_BALL),))
    f.reader.read_pc_items = lambda: ((int(ItemId.SILPH_SCOPE), 1),)
    source = "wild:PokemonTower3F:grass"
    provider = RedAreaSurveyGoalProvider(source_id=source,
        area_executor=_AreaExecutor(f.reader, f.actions, source_id=source), actions=f.actions,
        emulator=f.port, adapter=f.adapter, required_capture_items=(ItemId.SILPH_SCOPE,))
    spec = SimpleNamespace(parameters={"map_id": int(MapId.POKEMON_TOWER_3F), "player_x": 4, "player_y": 2})
    initial = f.adapter.observe()
    fresh = FreshRedGoalObservation("0" * 64, initial, f.port.observe())
    seen = []
    handler = SimpleNamespace(verified_trainer_income=0 if fault == "unverified_income" else 200)
    def wrapper(inner, bound_spec):
        assert bound_spec is spec
        seen.append("wrapped")
        return handler
    f.router.interruption_handler_wrapper = wrapper
    monkeypatch.setattr(items, "prepare_center_departure", lambda *a: None)
    def travel(route, *args, interruption_handler, **kwargs):
        assert interruption_handler is handler
        if fault == "trainer_stop":
            raise RouteExecutionError("retained trainer stop")
        f.reader.raw = replace(f.reader.raw, map_id=route.terminal_map, player_y=4, player_x=13,
                               player_money=700)
        seen.append("trainer")
        return SimpleNamespace(passed=True)
    monkeypatch.setattr(items, "execute_route", travel)
    monkeypatch.setattr(items, "face_pc_boundary", lambda *a: None)
    monkeypatch.setattr(items, "open_reds_pc", lambda *a: seen.append("pc"))
    monkeypatch.setattr(items, "close_generic_pc_session", lambda *a: None)
    def withdraw(*args, **kwargs):
        f.reader.raw = replace(f.reader.raw, bag_items=(*f.reader.raw.bag_items, (int(ItemId.SILPH_SCOPE), 1)),
                               player_money=701 if fault == "withdrawal_cash" else 700)
        return SimpleNamespace(passed=True)
    monkeypatch.setattr(items, "withdraw_single_pc_item", withdraw)
    selected = ExecutableGoalBinding("pokemon.red:acquisition:" + source, GoalKind.ACQUIRE_SPECIES,
        .1, .1, lambda: seen.append("capture") or GoalExecutionReport(0, 0, {}),
        lambda _: GoalVerification.succeeded())
    from test_red_routed_capture_support import unavailable
    monkeypatch.setattr(type(f.router), "enumerate_routed_kinds", lambda *a, **k:
        GoalBindingSet((selected.opportunity, unavailable()), (selected,)))
    binding = items.bind_capture_item_support(f.router, spec, provider, initial, fresh, f.port)
    assert binding is not None and not seen
    if fault:
        with pytest.raises((RouteExecutionError, items.RedCaptureItemSupportError)):
            binding.execute()
        assert "capture" not in seen
        if fault in {"unverified_income", "trainer_stop"}:
            assert "pc" not in seen
    else:
        report = binding.execute()
        assert report.evidence["capture_item_support"]["verified_trainer_income"] == 200
        assert binding.verify(report).status.value == "succeeded"
        assert f.reader.raw.player_money == 700
        assert seen == ["wrapped", "trainer", "pc", "capture"]
