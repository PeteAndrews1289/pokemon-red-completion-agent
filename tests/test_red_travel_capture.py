"""ROM-free contradictory outcomes for the guarded travel-capture seam."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.red_collection import red_internal_species_id, red_species_ref
from pokemon_red_completion.red_travel_capture import (
    RedTravelCaptureError,
    RegisteredTravelCaptureHandler,
)
from pokemon_red_completion.route_executor import (
    InterruptionReceipt,
    RouteExecutionError,
    RouteExecutionFailureReason,
    RouteExecutionLimits,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.route_plan import plan_route


class Harness:
    def __init__(self, target=109):
        species = (7, 16, 25, 43, 74, 129)
        self.target = red_species_ref(target)
        self.raw = RawGameState(
            game_started=True,
            map_id=165,
            player_y=16,
            player_x=20,
            battle_state=1,
            enemy_species_id=red_internal_species_id(target),
            enemy_level=30,
            party_count=6,
            party_species_ids=tuple(map(red_internal_species_id, species)),
            party_hp=(30, 40, 50, 60, 70, 80),
            party_status=(0,) * 6,
            bag_items=((int(ItemId.POKE_BALL), 6),),
            player_money=8,
        )
        stock = tuple(
            LivingSpecimen(red_species_ref(n), 20 + i, CollectionLocation.PARTY, slot_index=i)
            for i, n in enumerate(species)
        )
        self.collection = CollectionObservation(
            frozenset(x.species_ref for x in stock), stock, 6, 6, (0, 0), 0, 20
        )
        self.frames = self.actions = self.calls = self.fallback_calls = 0
        self.extra_registered = frozenset()
        self.caught = True
        self.after_hook = lambda: None
        self.ready = True
        self.handler = RegisteredTravelCaptureHandler(
            self,
            self,
            SimpleNamespace(
                handle=self.fallback,
                handled_hazard_kinds=frozenset({"trainer_sight"}),
                handled_interruption_kinds=frozenset(
                    {"wild_battle", "scripted_dialogue"}
                ),
            ),
            lambda col: col.owned_species | self.extra_registered,
            frozenset({self.target}),
            {165: frozenset({self.target})},
            lambda: self.frames,
            lambda: self.actions,
        )
        self.start = TraversalSnapshot(165, (16, 20), False, "wild_battle", mode="land")

    def read(self):
        return self.raw

    def read_input_readiness(self):
        return SimpleNamespace(ready=self.ready)

    def read_collection(self):
        return self.collection

    def fallback(self, interruption):
        self.fallback_calls += 1
        return InterruptionReceipt(
            interruption.interruption, interruption.map_id, interruption.at, {"fallback": True}
        )

    def capture_encounter(self, species):
        assert species == self.target
        self.calls += 1
        self.actions += 2
        self.frames += 48
        self.raw = replace(self.raw, battle_state=0, bag_items=((int(ItemId.POKE_BALL), 5),))
        if self.caught:
            added = LivingSpecimen(species, 30, CollectionLocation.BOX)
            self.collection = replace(
                self.collection,
                specimens=(*self.collection.specimens, added),
                box_counts=(1, 0),
                owned_species=self.collection.owned_species | {species},
            )
        self.after_hook()
        return self.caught


@pytest.mark.parametrize("target", [95, 109, 81])
def test_missing_species_capture_verifies_physical_registration_and_resumes(target):
    h = Harness(target)
    receipt = h.handler.handle(h.start)
    assert receipt.resumed_map == 165 and receipt.resumed_at == (16, 20)
    assert receipt.details["captured"] is True
    assert receipt.details["species_ref"] == red_species_ref(target)
    assert receipt.details["new_registrations"] == 1
    assert receipt.details["balls_spent"] == 1
    assert receipt.details["actions"] == 2 and receipt.details["frames"] == 48
    assert receipt.details["destination_changed"] is False
    assert receipt.details["learned_encounter_choice"] is False
    assert h.calls == 1 and h.fallback_calls == 0
    assert h.handler.handled_hazard_kinds == frozenset({"trainer_sight"})
    assert h.handler.handled_interruption_kinds == frozenset(
        {"wild_battle", "scripted_dialogue"}
    )


@pytest.mark.parametrize(
    "reason",
    [
        "global_credit",
        "not_target",
        "not_ordinary",
        "no_balls",
        "box_full",
        "party_room",
        "ghost",
        "safari",
    ],
)
def test_ineligible_encounters_delegate_without_capture(reason):
    h = Harness()
    if reason == "global_credit":
        h.extra_registered = frozenset({h.target})
    elif reason == "not_target":
        h.handler.targets = frozenset()
    elif reason == "not_ordinary":
        h.handler.ordinary_species = {}
    elif reason == "no_balls":
        h.raw = replace(h.raw, bag_items=())
    elif reason == "box_full":
        h.collection = replace(h.collection, box_counts=(20, 0))
    elif reason == "party_room":
        h.collection = replace(h.collection, specimens=h.collection.specimens[:-1], party_size=5)
    elif reason == "ghost":
        h.raw = replace(h.raw, map_id=int(MapId.POKEMON_TOWER_3F))
        h.start = replace(h.start, map_id=int(MapId.POKEMON_TOWER_3F))
    else:
        h.raw = replace(h.raw, map_id=int(MapId.SAFARI_ZONE_EAST))
        h.start = replace(h.start, map_id=int(MapId.SAFARI_ZONE_EAST))
        h.handler.ordinary_species = {h.start.map_id: frozenset({h.target})}
    assert h.handler.handle(h.start).details == {"fallback": True}
    assert h.calls == 0 and h.fallback_calls == 1 and not h.handler.attempted


def test_trainer_remains_existing_handler_authority():
    h = Harness()
    h.raw = replace(h.raw, battle_state=2)
    h.handler.handle(replace(h.start, interruption="trainer_engagement"))
    assert h.calls == 0 and h.fallback_calls == 1


@pytest.mark.parametrize(
    "change", ["map", "position", "trainer", "missing_species", "fainted", "truncated", "status"]
)
def test_bad_entry_stops_before_capture(change):
    h = Harness()
    updates = {
        "map": {"map_id": 166},
        "position": {"player_x": 21},
        "trainer": {"battle_state": 2},
        "missing_species": {"enemy_species_id": None},
        "fainted": {"party_hp": (0, 40, 50, 60, 70, 80)},
        "truncated": {"party_status": (0,)},
        "status": {"party_status": (8, 0, 0, 0, 0, 0)},
    }
    h.raw = replace(h.raw, **updates[change])
    with pytest.raises(RedTravelCaptureError):
        h.handler.handle(h.start)
    assert h.calls == 0 and h.fallback_calls == 0


@pytest.mark.parametrize(
    "change",
    [
        "moved",
        "battle",
        "not_ready",
        "fainted",
        "status",
        "species",
        "stock_loss",
        "wrong_catch",
        "lost_credit",
        "wrong_box",
        "no_spend",
        "money",
        "actions",
        "frames",
    ],
)
def test_unverified_exit_poisoned_without_fallback_or_retry(change):
    h = Harness()

    def corrupt():
        if change == "moved":
            h.raw = replace(h.raw, player_x=21)
        elif change == "battle":
            h.raw = replace(h.raw, battle_state=1)
        elif change == "not_ready":
            h.ready = False
        elif change == "fainted":
            h.raw = replace(h.raw, party_hp=(0, 40, 50, 60, 70, 80))
        elif change == "status":
            h.raw = replace(h.raw, party_status=(8, 0, 0, 0, 0, 0))
        elif change == "species":
            h.raw = replace(h.raw, party_species_ids=(1,) * 6)
        elif change == "stock_loss":
            h.collection = replace(
                h.collection,
                specimens=(
                    replace(h.collection.specimens[0], level=99),
                    *h.collection.specimens[1:],
                ),
            )
        elif change == "wrong_catch":
            h.collection = replace(
                h.collection,
                specimens=(
                    *h.collection.specimens[:-1],
                    replace(h.collection.specimens[-1], species_ref=red_species_ref(95)),
                ),
            )
        elif change == "lost_credit":
            h.collection = replace(h.collection, owned_species=frozenset({h.target}))
        elif change == "wrong_box":
            h.collection = replace(h.collection, box_counts=(0, 1))
        elif change == "no_spend":
            h.raw = replace(h.raw, bag_items=((int(ItemId.POKE_BALL), 6),))
        elif change == "money":
            h.raw = replace(h.raw, player_money=100)
        elif change == "actions":
            h.actions = 513
        elif change == "frames":
            h.frames = 120_001

    h.after_hook = corrupt
    with pytest.raises(RedTravelCaptureError):
        h.handler.handle(h.start)
    with pytest.raises(RedTravelCaptureError, match="incomplete"):
        h.handler.handle(h.start)
    assert h.calls == 1 and h.fallback_calls == 0


def test_failed_capture_is_not_registration_and_keeps_spending():
    h = Harness()
    h.caught = False
    receipt = h.handler.handle(h.start)
    assert receipt.details["captured"] is False and receipt.details["new_registrations"] == 0
    assert receipt.details["balls_spent"] == 1 and h.target not in h.collection.owned_species


def test_one_capture_attempt_per_route_even_when_another_missing_species_appears():
    h = Harness()
    h.handler.handle(h.start)
    h.raw = replace(h.raw, battle_state=1, enemy_species_id=red_internal_species_id(95))
    h.handler.targets = frozenset({red_species_ref(95)})
    h.handler.handle(h.start)
    assert h.calls == 1 and h.fallback_calls == 1


def test_controller_error_does_not_flee_or_repeat():
    h = Harness()

    def fail():
        raise RuntimeError("interrupted controller")

    h.after_hook = fail
    with pytest.raises(RedTravelCaptureError, match="controller failed") as error:
        h.handler.handle(h.start)
    assert isinstance(error.value.__cause__, RuntimeError)
    assert str(error.value.__cause__) == "interrupted controller"
    with pytest.raises(RedTravelCaptureError, match="incomplete"):
        h.handler.handle(h.start)
    assert h.calls == 1 and h.fallback_calls == 0


@pytest.mark.parametrize("eligible", [True, False])
def test_registration_lookup_must_not_advance_game_even_before_fallback(eligible):
    h = Harness()

    def bad_lookup(col):
        h.frames += 1
        return col.owned_species if eligible else col.owned_species | {h.target}

    h.handler.registered = bad_lookup
    with pytest.raises(RedTravelCaptureError, match="eligibility dispatched"):
        h.handler.handle(h.start)
    assert h.calls == 0 and h.fallback_calls == 0


def test_target_can_escape_without_a_throw_but_cannot_gain_registration():
    h = Harness()
    h.caught = False
    h.after_hook = lambda: setattr(
        h, "raw", replace(h.raw, bag_items=((int(ItemId.POKE_BALL), 6),))
    )
    receipt = h.handler.handle(h.start)
    assert receipt.details["balls_spent"] == 0 and receipt.details["new_registrations"] == 0


@pytest.mark.parametrize(
    "items",
    [
        ((int(ItemId.POKE_BALL), 4), (int(ItemId.GREAT_BALL), 1)),
        ((int(ItemId.POKE_BALL), 5), (int(ItemId.POTION), 1)),
    ],
)
def test_ball_total_does_not_hide_resource_fabrication(items):
    h = Harness()
    h.after_hook = lambda: setattr(h, "raw", replace(h.raw, bag_items=items))
    with pytest.raises(RedTravelCaptureError, match="ball delta"):
        h.handler.handle(h.start)


@pytest.mark.parametrize(
    "field,value", [("maximum_capture_actions", 0), ("maximum_capture_frames", True)]
)
def test_invalid_bounds_rejected(field, value):
    h = Harness()
    setattr(h.handler, field, value)
    with pytest.raises(ValueError):
        h.handler.__post_init__()


class TravelWorld:
    """Small varied route; the production route executor owns all decisions."""

    def __init__(self, harness, *, blocked=False):
        self.h = harness
        self.blocked = blocked
        self.moves = []

    def observe(self):
        raw = self.h.raw
        return TraversalSnapshot(
            raw.map_id,
            (raw.player_y, raw.player_x),
            self.h.ready and not raw.battle_state,
            "wild_battle" if raw.battle_state else None,
            mode="land",
        )

    def execute(self, action):
        self.h.actions += 1
        self.h.frames += 24
        if action.kind is MacroActionKind.WAIT:
            return
        assert action.kind is MacroActionKind.MOVE
        assert self.h.raw.battle_state == 0
        self.moves.append(action.value)
        if not self.blocked:
            dy, dx = {"right": (0, 1), "up": (-1, 0)}[action.value]
            self.h.raw = replace(
                self.h.raw, player_y=self.h.raw.player_y + dy, player_x=self.h.raw.player_x + dx
            )


def travel_plan():
    local = LocalGraph(
        {
            (16, 20): (LocalEdge((16, 21), "right"),),
            (16, 21): (LocalEdge((15, 21), "up"),),
            (15, 21): (),
        }
    )
    return plan_route(MacroGraph({165: ()}), {165: local}, 165, (16, 20), 165, goal_at=(15, 21))


@pytest.mark.parametrize("target,caught", [(95, True), (109, True), (81, False)])
def test_production_route_executor_resumes_original_route_after_capture(target, caught):
    h = Harness(target)
    h.caught = caught
    world = TravelWorld(h)
    plan = travel_plan()
    report = execute_route(plan, world, world, interruption_handler=h.handler)
    assert report.passed
    assert report.initial_plan is plan
    assert report.terminal.at == (15, 21)
    assert world.moves == ["right", "up"]
    assert len(report.interruptions) == 1
    assert report.interruptions[0].details["new_registrations"] == int(caught)
    assert report.interruptions[0].details["learned_encounter_choice"] is False
    assert report.replans == ()
    assert h.calls == 1


def test_later_route_failure_retains_capture_without_claiming_destination_success():
    h = Harness()
    world = TravelWorld(h, blocked=True)
    plan = travel_plan()
    with pytest.raises(RouteExecutionError) as error:
        execute_route(
            plan,
            world,
            world,
            interruption_handler=h.handler,
            limits=RouteExecutionLimits(max_step_attempts=1, replan_after_unchanged=1),
        )
    failure = error.value.failure
    assert failure is not None
    assert failure.initial_plan is plan
    assert failure.last_observation.at == (16, 20)
    assert failure.movement_requests == 1
    assert failure.interruptions[0].details["new_registrations"] == 1
    assert failure.interruptions[0].details["destination_changed"] is False
    assert h.target in h.collection.owned_species
    assert dict(h.raw.bag_items)[int(ItemId.POKE_BALL)] == 5
    assert h.calls == 1 and h.fallback_calls == 0


def test_controller_failure_attaches_route_trace_and_preserves_original_cause():
    h = Harness()

    def fail():
        raise RuntimeError("interrupted controller")

    h.after_hook = fail
    world = TravelWorld(h)
    with pytest.raises(RedTravelCaptureError) as error:
        execute_route(travel_plan(), world, world, interruption_handler=h.handler)
    failure = error.value.failure
    assert failure is not None
    assert failure.reason is RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED
    assert failure.movement_requests == 0
    assert failure.interruptions == ()  # The catch has not passed its verifier.
    assert isinstance(error.value.__cause__, RuntimeError)
    assert str(error.value.__cause__) == "interrupted controller"
    assert h.actions == 2 and h.frames == 48  # Dispatched work is not refunded.
    assert h.calls == 1 and h.fallback_calls == 0


@pytest.mark.parametrize("fault", [None, "append", "swapped", "level", "other_box", "missing"])
def test_nonempty_box_capture_requires_prepend_and_preserves_every_old_specimen(fault):
    h = Harness()
    party = h.collection.specimens
    elsewhere = LivingSpecimen(red_species_ref(19), 7, CollectionLocation.BOX, 0, 0)
    first = LivingSpecimen(red_species_ref(42), 22, CollectionLocation.BOX, 1, 0)
    second = LivingSpecimen(red_species_ref(75), 25, CollectionLocation.BOX, 1, 1)
    h.collection = replace(
        h.collection, specimens=(*party, elsewhere, first, second),
        owned_species=(
            h.collection.owned_species | {s.species_ref for s in (elsewhere, first, second)}
        ),
        current_box_index=1, box_counts=(1, 2),
    )
    before = h.collection

    def game_result():
        new = LivingSpecimen(h.target, 30, CollectionLocation.BOX, 1, 0)
        preserved = [elsewhere, replace(first, slot_index=1), replace(second, slot_index=2)]
        if fault == "append":
            new = replace(new, slot_index=2)
            preserved = [elsewhere, first, second]
        elif fault == "swapped":
            preserved = [elsewhere, replace(first, slot_index=2), replace(second, slot_index=1)]
        elif fault == "level":
            preserved[1] = replace(preserved[1], level=23)
        elif fault == "other_box":
            preserved[0] = replace(elsewhere, level=8)
        elif fault == "missing":
            preserved.pop()
        h.collection = replace(
            before, specimens=(*party, *preserved, new), box_counts=(1, 3),
            owned_species=before.owned_species | {h.target},
        )

    h.after_hook = game_result
    if fault is None:
        receipt = h.handler.handle(h.start)
        assert receipt.details["captured"] is True
        assert receipt.details["new_registrations"] == 1
        assert h.collection.box_counts == (1, 3)
        assert h.collection.current_box_index == 1
    else:
        with pytest.raises(RedTravelCaptureError, match="collection or ball delta"):
            h.handler.handle(h.start)
    assert h.calls == 1 and h.fallback_calls == 0
