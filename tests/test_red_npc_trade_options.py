from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_npc_trade import TRADE, member, observation

import pokemon_red_completion.red_npc_trade_options as module
from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import EventFlag
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.red_collection import red_species_ref as ref
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def fixture(monkeypatch, *, boxed=False, full=False):
    obs = observation()
    if boxed:
        c = obs.collection_observation
        c.specimens = (*c.specimens[:-1], replace(c.specimens[-1], location=CollectionLocation.BOX))
    members = tuple(member(i + 1, 1) for i in range(6)) if full else (member(1, 148),)
    obs.party = PartyObservation(members)
    events = bytearray(320)
    flag = int(EventFlag.GOT_POKEDEX)
    events[flag // 8] |= 1 << (flag % 8)
    raw = replace(obs.raw, party_count=len(members), event_flags=bytes(events))
    obs.raw = raw
    r = NS(
        read_bottom_dialogue_box_visible=lambda: False,
        read_safari_session_state=lambda: NS(has_active_session=False),
        read_pending_trainer_battle_identity=lambda: None,
        read_fly_menu_state=lambda: None,
        read_completed_npc_trades=lambda: frozenset(),
        read_current_box_state=lambda: NS(species_ids=(), box_index=0),
        read_all_box_states=lambda: (),
        read_fly_destinations=lambda: (2,),
    )
    policy = NS(protected_counts={}, goal_registered=lambda c: c.owned_species)
    emulator = NS(frame_count=0, pressed_buttons=frozenset())
    runtime = NS(
        npc_trades=True,
        reader=r,
        emulator=emulator,
        adapter=NS(observe=lambda: obs),
        registration_policy=policy,
    )
    start = TraversalSnapshot(48 if not boxed else 2, (2, 4), True, mode="land")
    calls = []
    actions = CountingExecutor(NS(execute=lambda a: calls.append(a)))
    monkeypatch.setattr(module, "stationary_npc_trades", lambda _: (TRADE,))
    monkeypatch.setattr(module, "PokemonRedPartyReader", lambda _: NS(read=lambda: obs.party))
    monkeypatch.setattr(module, "Gen1TraversalObserver", lambda *a, **k: NS(observe=lambda: start))
    monkeypatch.setattr(module, "_supported_plan", lambda *a, **k: True)
    monkeypatch.setattr(module, "internal_to_dex", lambda _: {148: 63, 42: 122})
    plan = NS(cost=1, steps=(1,))
    world = NS(
        rom=b"unused",
        plan_feasible_to_map=lambda *a, **k: plan,
        rules=NS(cut_block_swaps=(NS(before=50, after=109),)),
    )
    return runtime, obs, actions, world, calls


def test_default_off_never_observes_or_inputs():
    assert module.npc_trade_bindings(NS(), None, None, None) == ()


def test_party_ready_direct_route_needs_no_fly_or_town_detour(monkeypatch):
    runtime, obs, actions, world, calls = fixture(monkeypatch)
    start = TraversalSnapshot(13, (9, 5), True, mode="land")
    monkeypatch.setattr(module, "Gen1TraversalObserver", lambda *a, **k: NS(observe=lambda: start))
    runtime.reader.read_fly_destinations = lambda: ()
    assert len(module.npc_trade_bindings(runtime, obs, actions, world)) == 1
    assert not calls


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "completed",
        "registered",
        "protected",
        "dialogue",
        "pending",
        "no_route",
        "full_box",
        "no_pokedex",
    ],
)
def test_discovery_masks_unavailable_offers_without_inputs(monkeypatch, damage):
    runtime, obs, actions, world, calls = fixture(monkeypatch, boxed=True, full=True)
    if damage == "completed":
        runtime.reader.read_completed_npc_trades = lambda: frozenset({1})
    elif damage == "registered":
        obs.collection_observation.owned_species |= {ref(122)}
    elif damage == "protected":
        runtime.registration_policy.protected_counts = {ref(63): 1}
    elif damage == "dialogue":
        runtime.reader.read_bottom_dialogue_box_visible = lambda: True
    elif damage == "pending":
        runtime.reader.read_pending_trainer_battle_identity = lambda: (201, 1)
    elif damage == "no_route":

        def unavailable(*a, **k):
            raise RoutePlanningError("no route")

        world.plan_feasible_to_map = unavailable
    elif damage == "full_box":
        runtime.reader.read_current_box_state = lambda: NS(species_ids=(1,) * 20)
    elif damage == "no_pokedex":
        obs.raw = replace(obs.raw, event_flags=bytes(320))
    result = module.npc_trade_bindings(runtime, obs, actions, world)
    assert len(result) == int(damage is None)
    assert not calls and actions.actions_executed == runtime.emulator.frame_count == 0


@pytest.mark.parametrize("damage", ["frame", "flags", "boxes", "buttons"])
def test_binding_rejects_stale_origin_and_cannot_retry(monkeypatch, damage):
    runtime, obs, actions, world, calls = fixture(monkeypatch)
    (binding,) = module.npc_trade_bindings(runtime, obs, actions, world)
    assert binding.verify(GoalExecutionReport(1, 1, {})).status is GoalDecisionOutcome.FAILED
    if damage == "frame":
        runtime.emulator.frame_count = 1
    elif damage == "flags":
        runtime.reader.read_completed_npc_trades = lambda: frozenset({1})
    elif damage == "boxes":
        runtime.reader.read_all_box_states = lambda: (object(),)
    else:
        runtime.emulator.pressed_buttons = {"a"}
    with pytest.raises(module.RedNPCTradeError, match="origin changed"):
        binding.execute()
    with pytest.raises(module.RedNPCTradeError, match="already consumed"):
        binding.execute()
    assert not calls


def test_party_ready_execution_has_no_hidden_storage_operation(monkeypatch):
    runtime, obs, actions, world, calls = fixture(monkeypatch)
    world.replanner = lambda: None

    def field_port(*a, **k):
        assert k == {"cut_block_swaps": {50: 109}}
        return NS(cut_receipts=())

    monkeypatch.setattr(module, "Gen1FieldMovePort", field_port)
    monkeypatch.setattr(module, "execute_route", lambda *a, **k: NS(passed=True, executed_steps=()))
    current = [obs]
    runtime.adapter.observe = lambda: current[0]

    def exchange(*a, **k):
        assert k == dict(source_slot=1, source_species_id=148, target_species_id=42)
        current[0] = observation(True)
        runtime.reader.read_completed_npc_trades = lambda: frozenset({1})
        actions.actions_executed += 1
        runtime.emulator.frame_count += 180
        return {"received_level": 10}

    monkeypatch.setattr(module, "execute_adjacent_trade", exchange)
    (binding,) = module.npc_trade_bindings(runtime, obs, actions, world)
    report = binding.execute()
    assert report.evidence["boxed_source"] is False
    assert report.actions_executed == 1 and report.frames_executed == 180
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    current[0].raw = replace(current[0].raw, player_money=1)
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
