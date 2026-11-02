from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.red_scripted_gift as module
from pokemon_red_completion.collection import CollectionLocation as Location
from pokemon_red_completion.collection import LivingSpecimen
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_acquisition import (
    AcquisitionSource,
    MapObject,
    ScriptedAcquisition,
)
from pokemon_red_completion.observation import (
    EventFlag,
    OverworldMovementMode,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError

GIFT = module.RedScriptedGift(131, 15, 212, 1, 44, (5, 1))


def observation(*, owned=False, size=6):
    events = bytearray(320)
    flag = int(EventFlag.BEAT_SILPH_CO_GIOVANNI)
    events[flag // 8] |= 1 << (flag % 8)
    specimens = tuple(
        LivingSpecimen(red_species_ref(1), 30, Location.PARTY, 0, i) for i in range(size)
    )
    # Duplicate boxed specimens expose the set-vs-multiset verification trap.
    specimens += tuple(
        LivingSpecimen(red_species_ref(63), 12, Location.BOX, 2, i) for i in range(2)
    )
    if owned:
        specimens += (
            LivingSpecimen(GIFT.species_ref, 15, Location.BOX if size == 6 else Location.PARTY),
        )
    return NS(
        raw=RawGameState(
            True,
            212,
            2,
            5,
            min(6, size + owned),
            0,
            event_flags=bytes(events),
            player_money=16468,
            bag_items=((3, 6),),
        ),
        input_ready=True,
        collection_observation=NS(
            owned_species=frozenset(
                {red_species_ref(1), red_species_ref(63)} | ({GIFT.species_ref} if owned else set())
            ),
            specimens=specimens,
        ),
        party=NS(members=tuple(range(size)) + (("new",) if owned and size < 6 else ())),
    )


def reader():
    return NS(
        read_silph_gift_received=lambda: False,
        read_current_box_state=lambda: NS(species_ids=()),
        read_safari_session_state=lambda: NS(has_active_session=False),
        read_overworld_movement_mode=lambda: OverworldMovementMode.WALKING,
        read_bottom_dialogue_box_visible=lambda: False,
        read_pending_trainer_battle_identity=lambda: None,
        read_fly_menu_state=lambda: None,
    )


@pytest.mark.parametrize("flags,expected", [(0, False), (1, True), (16, False), (255, True)])
def test_observation_reads_real_gift_flag_not_registration(flags, expected):
    reads = []

    def read(at):
        reads.append(at)
        return flags

    assert PokemonRedStateReader(NS(read_u8=read)).read_silph_gift_received() is expected
    assert reads == [RamAddress.STATUS_FLAGS_4]


@pytest.mark.parametrize("size", [1, 5, 6])
def test_exact_gift_transition_and_capacity(size):
    assert module.gift_available(reader(), observation(size=size), GIFT)
    assert module.verify_gift_transition(
        observation(size=size), observation(owned=True, size=size), GIFT, received=True
    )


def test_outside_gift_floor_requires_native_access_door():
    obs = observation()
    obs.raw = replace(obs.raw, map_id=10)
    assert not module.gift_available(reader(), obs, GIFT)
    events = bytearray(obs.raw.event_flags)
    flag = int(EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2)
    events[flag // 8] |= 1 << (flag % 8)
    obs.raw = replace(obs.raw, event_flags=bytes(events))
    assert module.gift_available(reader(), obs, GIFT)


@pytest.mark.parametrize(
    "change",
    [
        "money",
        "bag",
        "party",
        "lost_duplicate",
        "extra",
        "wrong_level",
        "missing_flag",
        "not_ready",
        "battle",
        "map",
        "extra_registration",
        "missing_registration",
    ],
)
def test_verifier_rejects_false_success(change):
    before, after = observation(), observation(owned=True)
    if change == "money":
        after.raw = replace(after.raw, player_money=16467)
    if change == "bag":
        after.raw = replace(after.raw, bag_items=())
    if change == "party":
        after.party = NS(members=(99, *after.party.members[1:]))
    if change == "lost_duplicate":
        after.collection_observation.specimens = (
            *after.collection_observation.specimens[:6],
            *after.collection_observation.specimens[7:],
        )
    if change == "extra":
        after.collection_observation.specimens += (after.collection_observation.specimens[-1],)
    if change == "wrong_level":
        after.collection_observation.specimens = (
            *after.collection_observation.specimens[:-1],
            replace(after.collection_observation.specimens[-1], level=16),
        )
    if change == "not_ready":
        after.input_ready = False
    if change == "battle":
        after.raw = replace(after.raw, battle_state=1)
    if change == "map":
        after.raw = replace(after.raw, map_id=7)
    if change == "extra_registration":
        after.collection_observation.owned_species |= {red_species_ref(150)}
    if change == "missing_registration":
        after.collection_observation.owned_species = before.collection_observation.owned_species
    assert not module.verify_gift_transition(before, after, GIFT, received=change != "missing_flag")


@pytest.mark.parametrize(
    "change",
    [
        "already_received",
        "registered",
        "full",
        "battle",
        "story",
        "unready",
        "safari",
        "surf",
        "dialogue",
        "pending",
        "fly_menu",
    ],
)
def test_unavailable_gifts_never_become_offers(change):
    r, obs = reader(), observation()
    if change == "already_received":
        r.read_silph_gift_received = lambda: True
    if change == "registered":
        obs = observation(owned=True)
    if change == "full":
        r.read_current_box_state = lambda: NS(species_ids=(1,) * 20)
    if change == "battle":
        obs.raw = replace(obs.raw, battle_state=2)
    if change == "story":
        obs.raw = replace(obs.raw, event_flags=bytes(320))
    if change == "unready":
        obs.input_ready = False
    if change == "safari":
        r.read_safari_session_state = lambda: NS(has_active_session=True)
    if change == "surf":
        r.read_overworld_movement_mode = lambda: OverworldMovementMode.SURFING
    if change == "dialogue":
        r.read_bottom_dialogue_box_visible = lambda: True
    if change == "pending":
        r.read_pending_trainer_battle_identity = lambda: (201, 1)
    if change == "fly_menu":
        r.read_fly_menu_state = lambda: object()
    assert not module.gift_available(r, obs, GIFT)


@pytest.mark.parametrize("species,level", [(131, 15), (133, 25)])
def test_species_and_level_come_from_cartridge(monkeypatch, species, level):
    rom = bytearray(0x51DD0)
    rom[0x51D8E:0x51D96] = bytes.fromhex("08 fa 2e d7 cb 47 28 0f")
    rom[0x51DC3:0x51DC8] = bytes.fromhex("21 2e d7 cb c6")
    monkeypatch.setattr(
        module,
        "direct_gifts",
        lambda _: (None, ScriptedAcquisition(species, level, AcquisitionSource.GIFT)),
    )
    monkeypatch.setattr(
        module, "map_objects", lambda _: {212: (MapObject(212, 44, 6, 3, 255, 255, 1, ()),)}
    )
    decoded = module.silph_gift(bytes(rom))
    assert (decoded.species, decoded.level, decoded.at) == (species, level, (6, 3))
    for at in (0x51D8E, 0x51D90, 0x51D95, 0x51DC6):
        corrupt = bytearray(rom)
        corrupt[at] ^= 1
        with pytest.raises(module.CartridgeReadError):
            module.silph_gift(bytes(corrupt))


def test_disabled_family_does_not_touch_runtime():
    assert module.scripted_gift_bindings(NS(scripted_gifts=False), None, None, None) == ()


def setup_binding(monkeypatch):
    obs, r = observation(), reader()
    calls = []
    emulator = NS(frame_count=0, pressed_buttons=frozenset())
    actions = CountingExecutor(NS(execute=lambda a: calls.append(a)))
    runtime = NS(scripted_gifts=True, reader=r, emulator=emulator, adapter=NS(observe=lambda: obs))
    start = TraversalSnapshot(212, (5, 2), True, mode="land")
    monkeypatch.setattr(module, "silph_gift", lambda _: GIFT)
    monkeypatch.setattr(module, "PokemonRedPartyReader", lambda _: NS(read=lambda: obs.party))
    monkeypatch.setattr(module, "Gen1TraversalObserver", lambda *a, **k: NS(observe=lambda: start))
    monkeypatch.setattr(module, "_supported_plan", lambda *a, **k: True)
    plan = NS(cost=1, steps=(1,))
    world = NS(rom=b"unused", plan_feasible_to_map=lambda *a, **k: plan)
    return runtime, obs, actions, world, calls


def test_discovery_is_input_free_and_stale_origin_refuses(monkeypatch):
    runtime, obs, actions, world, calls = setup_binding(monkeypatch)
    bindings = module.scripted_gift_bindings(runtime, obs, actions, world)
    assert len(bindings) == 1 and not calls
    assert actions.actions_executed == runtime.emulator.frame_count == 0
    runtime.emulator.frame_count = 1
    with pytest.raises(module.RedScriptedGiftError, match="origin changed"):
        bindings[0].execute()
    with pytest.raises(module.RedScriptedGiftError, match="already attempted"):
        bindings[0].execute()
    assert not calls


def test_no_route_means_no_offer(monkeypatch):
    runtime, obs, actions, world, calls = setup_binding(monkeypatch)

    def fail(*a, **k):
        raise RoutePlanningError("blocked")

    world.plan_feasible_to_map = fail
    assert module.scripted_gift_bindings(runtime, obs, actions, world) == ()
    assert not calls


@pytest.mark.parametrize("failure", [None, "route", "object", "dialogue", "battle"])
def test_metered_executor_and_independent_verification(monkeypatch, failure):
    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.goal_manager import GoalDecisionOutcome
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport

    runtime, obs, actions, world, calls = setup_binding(monkeypatch)
    r = runtime.reader
    world.replanner = lambda: None
    r.read_current_map_objects = lambda: (
        () if failure == "object" else (NS(sprite_index=1, picture_id=44, at=(5, 1)),)
    )
    r.read_player_facing = lambda: "left"
    r.read_input_readiness = lambda: NS(ready=True)
    r.read = lambda: replace(obs.raw, battle_state=1 if failure == "battle" else 0)
    current = [obs]
    runtime.adapter.observe = lambda: current[0]

    def dispatch(action):
        calls.append(action)
        runtime.emulator.frame_count += 1
        if action.kind is MacroActionKind.CANCEL and failure is None:
            current[0] = observation(owned=True)
            r.read_silph_gift_received = lambda: True

    actions = CountingExecutor(NS(execute=dispatch))
    monkeypatch.setattr(module, "Gen1FieldMovePort", lambda *a: NS())
    monkeypatch.setattr(
        module, "execute_route", lambda *a, **k: NS(passed=failure != "route", executed_steps=())
    )
    (binding,) = module.scripted_gift_bindings(runtime, obs, actions, world)
    # A fabricated report before execution never grants credit.
    assert binding.verify(GoalExecutionReport(1, 1, {})).status is GoalDecisionOutcome.FAILED
    if failure:
        with pytest.raises(module.RedScriptedGiftError):
            binding.execute()
        assert len(calls) <= 97
        return
    report = binding.execute()
    assert report.actions_executed == len(calls) == 4
    assert report.frames_executed == runtime.emulator.frame_count == 4
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    current[0].raw = replace(current[0].raw, player_money=0)
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    with pytest.raises(module.RedScriptedGiftError, match="already attempted"):
        binding.execute()
