from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_story_travel as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


def setup(monkeypatch):
    raw = N(
        map_id=41,
        party_hp=(20,),
        player_money=1600,
        bag_items=((4, 5),),
        party_species_ids=(177,),
        badge_bits=0,
        facts=frozenset(),
    )
    lesson = {"completed_objectives": ["receive_pokedex"]}
    objective = N(id="reach_pewter", completion_facts=frozenset({"location:pewter_city"}))
    rt = N(
        emulator=N(frame_count=0, save_state_bytes=lambda: b"state"),
        reader=N(read=lambda: raw),
        adapter=N(
            graph=N(objective=lambda _: objective, available_objectives=lambda _: (objective,))
        ),
        observer=N(
            latch_verified_facts=lambda _: lesson["completed_objectives"].append("reach_pewter")
        ),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(
        s,
        "capture_player_lesson_snapshot",
        lambda _: (N(raw=raw, game_state=object()), {k: list(v) for k, v in lesson.items()}),
    )
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: object())
    monkeypatch.setattr(s, "semantic_facts", lambda r: r.facts)

    @dataclass
    class Route:
        rom: bytes = b"rom"
        destination_map: int = 0
        destination_at: tuple = (0, 0)

        @property
        def route_world(self):
            return N(
                plan_feasible_to_map=lambda *a: N(terminal_map=2, terminal_at=(35, 18), cost=248)
            )

        def __call__(self, *args):
            raw.map_id = self.destination_map
            raw.facts = objective.completion_facts
            actions.actions_executed += 1
            rt.emulator.frame_count += 16

    return rt, actions, Route(), raw, lesson


def test_travel_is_read_only_until_selected_and_does_not_claim_badge(monkeypatch):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    binding = s.story_travel_binding(rt, actions, objective_id="reach_pewter", route=route)
    assert actions.actions_executed == 0
    assert not binding.story_approach_only
    report = binding.execute()
    assert report.evidence["automatic_objectives"] == [] and raw.badge_bits == 0
    assert report.evidence["purchases"] == report.evidence["trainer_battles"] == 0
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert lesson["completed_objectives"] == ["receive_pokedex", "reach_pewter"]
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    raw.map_id = 41
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


def test_giovanni_uses_existing_travel_without_claiming_leader_reward(monkeypatch):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id="defeat_giovanni", completion_facts=frozenset({"badge:earth"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    # Merely reaching the gym cannot synthesize the badge fact.
    monkeypatch.setattr(s, "semantic_facts", lambda _: frozenset())
    binding = s.story_travel_binding(rt, actions, objective_id="defeat_giovanni", route=route)
    assert actions.actions_executed == 0
    assert binding.story_approach_only
    report = binding.execute()
    assert raw.map_id == int(s.MapId.VIRIDIAN_GYM)
    assert not report.evidence["objective_completed"]
    assert raw.badge_bits == 0 and "defeat_giovanni" not in lesson["completed_objectives"]


def test_silph_center_arrival_never_synthesizes_chapter_completion(monkeypatch):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id="liberate_silph", completion_facts=frozenset({"quest:silph_liberated"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    rt.observer.latch_verified_facts = lambda _: pytest.fail("arrival synthesized liberation")
    binding = s.story_travel_binding(rt, actions, objective_id="liberate_silph", route=route)
    assert actions.actions_executed == 0
    report = binding.execute()
    assert raw.map_id == int(s.MapId.SAFFRON_POKECENTER)
    assert report.evidence["objective_completed"] is False
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert "liberate_silph" not in lesson["completed_objectives"]


@pytest.mark.parametrize("objective_id", ["obtain_surf", "obtain_strength"])
def test_safari_approach_does_not_synthesize_hm_or_healing(monkeypatch, objective_id):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id=objective_id, completion_facts=frozenset({"move:" + objective_id}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    before_hp, before_bag = raw.party_hp, raw.bag_items
    binding = s.story_travel_binding(rt, actions, objective_id=objective_id, route=route)
    assert actions.actions_executed == 0 and binding.story_objective_ref == objective_id
    assert binding.story_approach_only
    report = binding.execute()
    assert raw.map_id == int(s.MapId.FUCHSIA_POKECENTER)
    assert not report.evidence["objective_completed"]
    assert raw.party_hp == before_hp and raw.bag_items == before_bag
    assert objective_id not in lesson["completed_objectives"]


def test_fuchsia_arrival_uses_the_existing_verified_travel_contract(monkeypatch):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id="reach_fuchsia", completion_facts=frozenset({"location:fuchsia_city"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    raw.facts = objective.completion_facts
    monkeypatch.setattr(
        s,
        "semantic_facts",
        lambda r: (
            objective.completion_facts if r.map_id == int(s.MapId.FUCHSIA_CITY) else frozenset()
        ),
    )
    latched = []
    rt.observer.latch_verified_facts = latched.append
    binding = s.story_travel_binding(rt, actions, objective_id="reach_fuchsia", route=route)
    assert actions.actions_executed == 0
    report = binding.execute()
    assert raw.map_id == int(s.MapId.FUCHSIA_CITY)
    assert latched == [objective.completion_facts]
    assert report.evidence["objective_completed"]


@pytest.mark.parametrize("enabled,permission", [(False, False), (True, False), (True, True)])
def test_cinnabar_surf_is_opt_in_and_uses_actual_native_permission(
    monkeypatch, enabled, permission
):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    route.allow_surf = True
    objective = N(id="reach_cinnabar", completion_facts=frozenset({"location:cinnabar_island"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    projectors, permissions = [], []

    def observer(*args, **kwargs):
        projectors.append(kwargs["capability_projector"])
        return N(observe=lambda: object())

    monkeypatch.setattr(s, "Gen1TraversalObserver", observer)
    monkeypatch.setattr(s, "cut_capabilities", lambda _: frozenset({"move:cut"}))
    monkeypatch.setattr(
        s, "surf_permission", lambda *a: permissions.append(a) or N(allowed=permission)
    )
    monkeypatch.setattr(
        s,
        "surf_capabilities",
        lambda raw, *, surf_allowed: frozenset({"move:surf"}) if surf_allowed else frozenset(),
    )
    rt.observer.latch_verified_facts = lambda _: lesson["completed_objectives"].append(
        "reach_cinnabar"
    )
    monkeypatch.setattr(
        s,
        "semantic_facts",
        lambda r: (
            objective.completion_facts if r.map_id == int(s.MapId.CINNABAR_ISLAND) else frozenset()
        ),
    )
    binding = s.story_travel_binding(
        rt, actions, objective_id="reach_cinnabar", route=route, allow_surf=enabled
    )
    expected = {"move:cut"} | ({"move:surf"} if enabled and permission else set())
    assert projectors[0](raw) == expected and len(permissions) == int(enabled)
    assert actions.actions_executed == 0
    report = binding.execute()
    assert raw.map_id == int(s.MapId.CINNABAR_ISLAND) and report.evidence["objective_completed"]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize("bad", [None, 0, 1, "yes"])
def test_story_surf_scope_rejects_non_boolean_before_any_observation(monkeypatch, bad):
    rt, actions, route, _, _ = setup(monkeypatch)
    with pytest.raises(TypeError, match="Surf"):
        s.story_travel_binding(
            rt, actions, objective_id="reach_cinnabar", route=route, allow_surf=bad
        )
    assert actions.actions_executed == 0


def test_surf_quote_cannot_bind_a_land_only_executor(monkeypatch):
    rt, actions, route, _, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="Surf-enabled"):
        s.story_travel_binding(
            rt, actions, objective_id="reach_cinnabar", route=route, allow_surf=True
        )
    assert actions.actions_executed == 0


@pytest.mark.parametrize("wrong_endpoint", [False, True])
def test_local_story_coordinate_preserves_objective_and_requires_exact_endpoint(
    monkeypatch, wrong_endpoint
):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id="defeat_erika", completion_facts=frozenset({"badge:rainbow"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    raw.map_id = s.DESTINATIONS["defeat_erika"]
    monkeypatch.setattr(
        s, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: N(at=(17, 4)))
    )
    monkeypatch.setattr(
        type(route),
        "route_world",
        property(
            lambda _: N(
                plan_feasible_to_map=lambda *a, **k: N(
                    terminal_map=134, terminal_at=(7, 5), cost=15
                )
            )
        ),
    )

    def travel(self, *args):
        raw.player_y, raw.player_x = (8, 5) if wrong_endpoint else self.destination_at
        actions.actions_executed += 1

    monkeypatch.setattr(type(route), "__call__", travel)
    binding = s.story_travel_binding(
        rt, actions, objective_id="defeat_erika", route=route, destination_at=(7, 5)
    )
    assert binding is not None and actions.actions_executed == 0
    if wrong_endpoint:
        with pytest.raises(RuntimeError):
            binding.execute()
    else:
        report = binding.execute()
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert not report.evidence["objective_completed"] and lesson["completed_objectives"] == [
            "receive_pokedex"
        ]


@pytest.mark.parametrize("target", [(1,), [-1, 2], (-1, 2), (True, 2)])
def test_invalid_local_story_coordinate_never_acts(monkeypatch, target):
    rt, actions, route, _, _ = setup(monkeypatch)
    with pytest.raises(ValueError):
        s.story_travel_binding(
            rt, actions, objective_id="defeat_erika", route=route, destination_at=target
        )
    assert actions.actions_executed == 0


def test_local_exact_target_still_refuses_cross_map_without_input(monkeypatch):
    rt, actions, route, raw, _ = setup(monkeypatch)
    objective = N(id="liberate_silph", completion_facts=frozenset())
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    assert raw.map_id != s.DESTINATIONS["liberate_silph"]
    assert s.story_travel_binding(
        rt, actions, objective_id="liberate_silph", route=route, destination_at=(3, 3)
    ) is None
    assert actions.actions_executed == 0


@pytest.mark.parametrize("failure", [None, "quote", "execution", "verification"])
def test_complete_cross_map_target_is_quoted_executed_and_verified(monkeypatch, failure):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id="liberate_silph", completion_facts=frozenset({"story:silph"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    quotes = []

    def plan(start, destination, *, goal_at):
        quotes.append((destination, goal_at))
        return N(terminal_map=destination,
                 terminal_at=(7, 3) if failure == "quote" else goal_at, cost=50)

    monkeypatch.setattr(
        type(route), "route_world", property(lambda _: N(plan_feasible_to_map=plan))
    )

    def travel(self, *args):
        raw.map_id = self.destination_map
        raw.player_y, raw.player_x = (7, 3) if failure == "execution" else self.destination_at
        actions.actions_executed += 1

    monkeypatch.setattr(type(route), "__call__", travel)
    binding = s.story_travel_binding(
        rt, actions, objective_id="liberate_silph", route=route,
        route_destination_at=(3, 3),
    )
    assert actions.actions_executed == 0
    assert quotes == [(s.DESTINATIONS["liberate_silph"], (3, 3))]
    if failure == "quote":
        assert binding is None
        return
    if failure == "execution":
        with pytest.raises(RuntimeError, match="destination"):
            binding.execute()
        return
    report = binding.execute()
    assert report.evidence["objective_completed"] is False
    assert lesson["completed_objectives"] == ["receive_pokedex"]
    if failure == "verification":
        raw.player_y = 7
    assert binding.verify(report).status is (
        GoalDecisionOutcome.FAILED if failure == "verification" else GoalDecisionOutcome.SUCCEEDED
    )


@pytest.mark.parametrize("scope", [
    {"destination_at": (3, 3)}, {"frontier": True},
    {"stop_at_map_boundary": True}, {"intermediate_map": 2},
    {"route_destination_at": (True, 3)}, {"route_destination_at": [3, 3]},
])
def test_complete_exact_route_rejects_partial_or_ambiguous_scope_before_observation(
    monkeypatch, scope
):
    rt, actions, route, _, _ = setup(monkeypatch)
    monkeypatch.setattr(
        s, "capture_player_lesson_snapshot", lambda _: pytest.fail("observed invalid scope")
    )
    with pytest.raises(ValueError, match="complete nonarrival"):
        s.story_travel_binding(
            rt, actions, objective_id="liberate_silph", route=route,
            **dict({"route_destination_at": (3, 3)}, **scope),
        )
    assert actions.actions_executed == 0


@pytest.mark.parametrize(
    "objective_id,fact",
    [("reach_lavender", "location:lavender_town"), ("reach_celadon", "location:celadon_city")],
)
def test_arrival_requires_its_observed_location_fact(monkeypatch, objective_id, fact):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id=objective_id, completion_facts=frozenset({fact}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    rt.observer.latch_verified_facts = lambda _: lesson["completed_objectives"].append(objective_id)

    def travel(self, *args):
        raw.map_id = self.destination_map
        raw.facts = objective.completion_facts
        actions.actions_executed += 1

    monkeypatch.setattr(type(route), "__call__", travel)
    binding = s.story_travel_binding(rt, actions, objective_id=objective_id, route=route)
    assert actions.actions_executed == 0
    report = binding.execute()
    assert report.evidence["objective_completed"] is True
    assert raw.map_id == s.DESTINATIONS[objective_id]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_stale_or_unavailable_destination_never_acts(monkeypatch):
    rt, actions, route, _, _ = setup(monkeypatch)
    binding = s.story_travel_binding(rt, actions, objective_id="reach_pewter", route=route)
    rt.emulator.save_state_bytes = lambda: b"different"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    rt.adapter.graph.available_objectives = lambda _: ()
    assert s.story_travel_binding(rt, actions, objective_id="reach_pewter", route=route) is None
    assert actions.actions_executed == 0


@pytest.mark.parametrize("certify", [False, True])
def test_declared_dialogue_route_does_not_use_a_text_forbidding_cash_certificate(
    monkeypatch, certify
):
    rt, actions, route, _, _ = setup(monkeypatch)
    called = []
    monkeypatch.setattr(
        s, "certified_cash_safe_transition", lambda *args: called.append(args) or None
    )
    binding = s.story_travel_binding(
        rt, actions, objective_id="reach_pewter", route=route, certify_cash_approach=certify
    )
    assert len(called) == int(certify) and actions.actions_executed == 0
    assert binding.maximum_cash_debit is None
    assert binding.verify(binding.execute()).status is GoalDecisionOutcome.SUCCEEDED


def test_declared_certificate_opt_out_has_a_distinct_ref_and_preserves_default_identity(
    monkeypatch,
):
    rt, actions, route, _, _ = setup(monkeypatch)
    default = s.story_travel_binding(rt, actions, objective_id="reach_pewter", route=route)
    explicit = s.story_travel_binding(
        rt, actions, objective_id="reach_pewter", route=route, certify_cash_approach=True
    )
    dialogue = s.story_travel_binding(
        rt, actions, objective_id="reach_pewter", route=route, certify_cash_approach=False
    )
    assert default.binding_ref == explicit.binding_ref
    assert default.binding_ref != dialogue.binding_ref and actions.actions_executed == 0


@pytest.mark.parametrize("invalid", [None, 1, "yes"])
def test_cash_certificate_scope_rejects_nonbooleans_before_input(monkeypatch, invalid):
    rt, actions, route, _, _ = setup(monkeypatch)
    with pytest.raises(TypeError, match="certification scope"):
        s.story_travel_binding(
            rt, actions, objective_id="reach_pewter", route=route, certify_cash_approach=invalid
        )
    assert actions.actions_executed == 0


@pytest.mark.parametrize(
    "objective_id", ["defeat_misty", "help_bill", "obtain_cut", "defeat_surge", "defeat_erika"]
)
def test_arrival_at_story_destination_never_awards_quest_credit(monkeypatch, objective_id):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id=objective_id, completion_facts=frozenset({"unearned:reward"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    rt.observer.latch_verified_facts = lambda _: pytest.fail("unearned completion")
    binding = s.story_travel_binding(rt, actions, objective_id=objective_id, route=route)
    report = binding.execute()
    assert raw.map_id == s.DESTINATIONS[objective_id]
    assert report.evidence["objective_completed"] is False
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert lesson["completed_objectives"] == ["receive_pokedex"]


def test_vermilion_arrival_requires_native_location_fact(monkeypatch):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    objective = N(id="reach_vermilion", completion_facts=frozenset({"location:vermilion_city"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    rt.observer.latch_verified_facts = lambda _: lesson["completed_objectives"].append(
        "reach_vermilion"
    )
    binding = s.story_travel_binding(rt, actions, objective_id="reach_vermilion", route=route)
    with pytest.raises(RuntimeError, match="protected resources"):
        binding.execute()  # fixture route supplies Pewter's fact, not Vermilion's
    assert "reach_vermilion" not in lesson["completed_objectives"]


@pytest.mark.parametrize("on_route", [True, False])
def test_intermediate_region_is_bound_to_actual_plan_without_story_credit(monkeypatch, on_route):
    rt, actions, route, _, lesson = setup(monkeypatch)
    monkeypatch.setattr(
        s,
        "Gen1TraversalObserver",
        lambda *a, **k: N(observe=lambda: N(map_id=41, last_outside_map=1)),
    )
    monkeypatch.setattr(
        s, "find_macro_path", lambda *a, **k: N(maps=(41, 14 if on_route else 15, 2))
    )

    def plan(start, destination):
        assert destination == 14
        return N(
            terminal_map=destination,
            terminal_at=(3, 3),
            cost=40,
            steps=(N(expected_map=14 if on_route else 15), N(expected_map=2)),
        )

    monkeypatch.setattr(
        type(route),
        "route_world",
        property(lambda _: N(plan_feasible_to_map=plan, macro_graph=object())),
    )
    if not on_route:
        with pytest.raises(ValueError, match="not on the planned"):
            s.story_travel_binding(
                rt, actions, objective_id="reach_pewter", route=route, intermediate_map=14
            )
        assert actions.actions_executed == 0
    else:
        binding = s.story_travel_binding(
            rt, actions, objective_id="reach_pewter", route=route, intermediate_map=14
        )
        report = binding.execute()
        assert report.evidence["objective_completed"] is False
        assert lesson["completed_objectives"] == ["receive_pokedex"]
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize(
    "field,value",
    [("player_money", 10), ("badge_bits", 1), ("party_species_ids", (1,)), ("bag_items", ())],
)
@pytest.mark.parametrize("certify", [False, True])
def test_travel_rejects_unexpected_resource_changes(monkeypatch, field, value, certify):
    rt, actions, route, raw, _ = setup(monkeypatch)
    from copy import copy

    observed = copy(raw)
    rt.reader.read = lambda: observed
    original = type(route).__call__

    def corrupt(self, *args):
        original(self, *args)
        observed.map_id, observed.facts = raw.map_id, raw.facts
        setattr(observed, field, value)

    monkeypatch.setattr(type(route), "__call__", corrupt)
    binding = s.story_travel_binding(
        rt, actions, objective_id="reach_pewter", route=route, certify_cash_approach=certify
    )
    with pytest.raises(RuntimeError, match="protected resources"):
        binding.execute()
