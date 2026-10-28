from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_goal_context as context
from pokemon_red_completion import red_native_boxed_evolution as native
from pokemon_red_completion import red_party_development_adapter as adapter
from pokemon_red_completion.gen1_cartridge import WildEncounterTable
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.party_development_outcome_learning import (
    canonical_party_development_outcome_model_sha256,
    upgrade_party_development_model_for_workload,
)
from pokemon_red_completion.red_collection import red_internal_species_id
from pokemon_red_completion.team_training import BalancedTeamPolicy
from test_party_development_outcome_learning import _initialized_model
import test_red_party_development_adapter as fixtures


@pytest.fixture
def menu_case(monkeypatch):
    observation = fixtures._observation()
    observation = replace(observation, party=PartyObservation(members=tuple(
        replace(member, experience=member.level ** 3 + 100)
        for member in observation.party.members
    )))
    venues = tuple(replace(venue, native_transport_ready=None) for venue in (
        context.ROUTE_11_TRAINING_VENUE, context.MANSION_TRAINING_VENUE,
    ))
    source = observation.party.members[0].species_id
    target = red_internal_species_id(51)
    volatile = next(iter(context.MANSION_VOLATILE_ENEMY_SPECIES))
    monkeypatch.setattr(context, "MANSION_VOLATILE_ENEMY_SPECIES", frozenset({volatile}))
    monkeypatch.setattr(context, "MANSION_ESCORT_ENEMY_SPECIES", frozenset())
    decoded = {
        venues[0].map_id: (WildEncounterTable("grass", 25, ((14, volatile),) + ((14, source),) * 9),),
        venues[1].map_id: (WildEncounterTable("grass", 25, ((30, source),) * 10),),
    }
    monkeypatch.setattr(adapter, "evolution_graph", lambda _: fixtures._evolutions())
    monkeypatch.setattr(adapter, "wild_encounter_tables", lambda _: decoded)
    monkeypatch.setattr(adapter, "RedPracticeCartridge", lambda _: SimpleNamespace(
        species=lambda species: SimpleNamespace(
            base_experience=101, experience_at_level=lambda level: level ** 3,
        )
    ))
    monkeypatch.setattr(native, "native_evolution_encounter_supported", lambda *a, **k: True)
    import pokemon_red_completion.red_team_training as training
    monkeypatch.setattr(training, "collection_finisher", lambda *a, **k: observation.party.members[1])
    monkeypatch.setattr(training, "collection_escape_escort", lambda *a, **k: observation.party.members[1])
    return SimpleNamespace(observation=observation, venues=venues, source=source,
                           target=target, decoded=decoded)


def build(case, **changes):
    arguments = dict(rom=b"unit-rom", trainee=case.observation.party.members[0],
                     target_species_id=case.target,
                     policy=BalancedTeamPolicy(minimum_level=30, required_size=3),
                     venues=case.venues, allow_guarded_escapes=True)
    arguments.update(changes)
    return adapter.build_native_evolution_venue_menu(case.observation, **arguments)


def select(case, model, state, events, venues=None, **changes):
    arguments = dict(rom=b"unit-rom", source_id=case.source, target_id=case.target,
        venues=case.venues if venues is None else venues, model=model,
        model_sha256="a" * 64, choice_state=state,
        actions=SimpleNamespace(record_diagnostic_event=lambda name, value: events.append((name, value))),
        excluded_helper_species=frozenset(), allow_guarded_escapes=True)
    arguments.update(changes)
    return native.select_native_evolution_model_venue(case.observation, **arguments)


def test_native_menu_uses_weighted_useful_slots_and_gen1_order_of_xp_division(menu_case):
    menu = build(menu_case)
    first, second = [dict(zip(menu.candidate_set.feature_names, row.features, strict=True))
                     for row in menu.candidate_set.candidates]
    assert first["venue.useful_encounter_share"] == 205 / 256
    assert first["venue.expected_recipient_xp_per_encounter"] == ((101 // 2) * 14 // 7) * 205 / 256 / 100_000
    assert second["venue.useful_encounter_share"] == 1
    assert second["venue.expected_recipient_xp_per_encounter"] == ((101 // 2) * 30 // 7) / 100_000
    assert first["level_workload.remaining_xp"] == (26 ** 3 - (22 ** 3 + 100)) / 2_000_000
    assert first["venue.travel_steps_known"] == first["venue.recovery_steps_known"] == 0
    assert menu.bindings == tuple(venue.band for venue in menu_case.venues)
    # Shared helpers can make a band legal even when the direct trainee is weak.
    assert second["venue.fightable_share"] < 1
    assert menu.candidate_available == (True, True)


def test_native_menu_is_identity_free_and_permutation_equivariant(menu_case):
    original = build(menu_case)
    renamed = tuple(replace(venue, band=replace(venue.band, area_id=f"unit-renamed-{i}"))
                    for i, venue in enumerate(menu_case.venues))
    other = build(menu_case, venues=renamed)
    assert [row.features for row in original.candidate_set.candidates] == [row.features for row in other.candidate_set.candidates]
    permuted = build(menu_case, venues=menu_case.venues[::-1])
    assert [row.features for row in original.candidate_set.candidates] == [row.features for row in permuted.candidate_set.candidates][::-1]
    assert original.semantic_snapshot_sha256 != other.semantic_snapshot_sha256


def test_native_menu_does_not_invent_missing_xp(menu_case):
    members = tuple(replace(member, experience=None) for member in menu_case.observation.party.members)
    case = SimpleNamespace(**vars(menu_case))
    case.observation = replace(menu_case.observation, party=PartyObservation(members=members))
    menu = build(case)
    values = dict(zip(menu.candidate_set.feature_names, menu.candidate_set.candidates[0].features, strict=True))
    assert values["level_workload.present"] == 0
    assert values["level_workload.remaining_xp"] == 0


@pytest.mark.parametrize("fault", ["transport", "coverage", "live_helper", "table", "battle"])
def test_native_menu_keeps_existing_executability_and_resource_gates(menu_case, monkeypatch, fault):
    case = menu_case
    if fault == "transport":
        case.venues = (replace(case.venues[0], native_transport_ready=lambda _: False), case.venues[1])
    elif fault == "coverage":
        monkeypatch.setattr(native, "native_evolution_encounter_supported", lambda *a, **k: False)
    elif fault == "live_helper":
        import pokemon_red_completion.red_team_training as training
        monkeypatch.setattr(training, "collection_finisher", lambda *a, **k: None)
    elif fault == "table":
        case.decoded[case.venues[0].map_id] = (WildEncounterTable("grass", 25, ((14, case.source),)),)
    else:
        case.observation = replace(case.observation, raw=replace(case.observation.raw, battle_state=1))
    with pytest.raises(adapter.RedPartyDevelopmentAdapterError):
        build(case)


def test_native_choice_is_scored_once_per_action_then_retains_exact_venue(menu_case):
    calls = []
    model = SimpleNamespace(predict=lambda menu: calls.append(menu) or 1)
    state, events = {}, []
    chosen = select(menu_case, model, state, events)
    assert chosen == menu_case.venues[1]
    assert select(menu_case, model, state, events) == chosen
    assert len(calls) == len(events) == 1
    assert events[0][0] == "native_evolution_venue_choice"
    assert events[0][1]["actor"] == "learned_venue_model"
    assert events[0][1]["selected_map_id"] == chosen.map_id
    assert events[0][1]["candidate_set"] is not None
    with pytest.raises(native.EvolutionVenueExhausted):
        select(menu_case, model, state, events, venues=(menu_case.venues[0],))
    with pytest.raises(context.RedGoalContextError, match="another action"):
        select(menu_case, model, state, events, target_id=red_internal_species_id(78))
    assert len(calls) == 1


@pytest.mark.parametrize("selected", [True, -1, 2, 1.5, None])
def test_native_referee_rejects_illegal_model_indices_without_substitution(menu_case, selected):
    events, state = [], {}
    with pytest.raises(context.RedGoalContextError, match="illegal binding"):
        select(menu_case, SimpleNamespace(predict=lambda _: selected), state, events)
    assert events == [] and state == {}


def test_native_referee_rejects_foreign_menu_bindings(menu_case, monkeypatch):
    menu = build(menu_case)
    monkeypatch.setattr(adapter, "build_native_evolution_venue_menu",
                        lambda *a, **k: replace(menu, bindings=menu.bindings[::-1]))
    with pytest.raises(context.RedGoalContextError, match="differs from executable"):
        select(menu_case, SimpleNamespace(predict=lambda _: 0), {}, [])


def test_forced_single_venue_is_support_not_a_learned_comparison(menu_case):
    model = SimpleNamespace(predict=lambda _: pytest.fail("singleton must not pretend to be a learned comparison"))
    events = []
    chosen = select(menu_case, model, {}, events, venues=(menu_case.venues[0],))
    assert chosen == menu_case.venues[0]
    assert events[0][1]["actor"] == "rule_based_support"
    assert events[0][1]["model_selected"] is False


def test_native_binder_authenticates_model_pair_and_preserves_model_authority():
    model = upgrade_party_development_model_for_workload(_initialized_model())
    digest = canonical_party_development_outcome_model_sha256(model)
    for arguments, message in [
        ({"venue_model": model}, "paired"),
        ({"venue_model_sha256": digest}, "paired"),
        ({"venue_model": model, "venue_model_sha256": "0" * 64}, "differs"),
        ({"venue_model": _initialized_model(), "venue_model_sha256": "0" * 64}, "differs"),
        ({"venue_model": model, "venue_model_sha256": digest,
          "prefer_highest_supported_venue": True}, "prefiltered"),
    ]:
        with pytest.raises(ValueError, match=message):
            native.bind_native_boxed_evolution(None, None, **arguments)


@pytest.mark.parametrize("use_model", [True, False])
@pytest.mark.parametrize("observer_fault", [False, True])
def test_native_training_observes_once_inside_nursing_cost_scope(tmp_path, monkeypatch, use_model, observer_fault):
    from test_red_native_boxed_evolution import runtime_fixture
    from test_red_goal_context import _ActionDelegate
    from pokemon_red_completion.executor import CountingExecutor
    from pokemon_red_completion.observation import MapId
    from pokemon_red_completion.red_team_training import EvolutionTrainingPaused
    runtime, reader, _ = runtime_fixture(tmp_path, count=1)
    monkeypatch.setattr(type(runtime.emulator), "save_state_bytes", lambda self: b"unchanged", raising=False)
    source, target = red_internal_species_id(77), red_internal_species_id(78)
    reader.raw = replace(reader.raw, map_id=MapId.CINNABAR_POKECENTER,
        party_species_ids=(*reader.raw.party_species_ids[:5], source),
        party_levels=(54, 55, 55, 55, 55, 32))
    candidates = (context.ROUTE_11_TRAINING_VENUE, context.DIGLETTS_CAVE_TRAINING_VENUE,
                  context.MANSION_TRAINING_VENUE)
    monkeypatch.setattr(native, "wild_tables", lambda _: {v.map_id: ((10, 0x21),) for v in candidates})
    # This unit isolates decision/nursing order; native transport has separate coverage.
    monkeypatch.setattr(native, "_mansion_transport_ready", lambda *a: True)
    order = []
    monkeypatch.setattr(native, "prepare_native_training_center", lambda *a: order.append("center"))
    monkeypatch.setattr(native, "restore_native_center_party", lambda *a: order.append("nurse") or 0)
    party = runtime.adapter.observe().party
    exact = replace(party, members=tuple(replace(member, experience=member.level ** 3 + 100)
                                        for member in party.members))
    monkeypatch.setattr(native, "PokemonRedPartyReader", lambda _: SimpleNamespace(read=lambda: exact))
    seen = []
    def choose(observation, **arguments):
        order.append("model")
        assert observation.party == exact
        assert tuple(v.map_id for v in arguments["venues"]) == tuple(v.map_id for v in candidates)
        assert all(v.move_slot is native.native_training_move_slot
                   and v.move_guard is native.native_training_move_guard for v in arguments["venues"])
        assert arguments["source_id"] == source and arguments["target_id"] == target
        seen.append(arguments)
        return arguments["venues"][0]
    monkeypatch.setattr(native, "select_native_evolution_model_venue", choose)
    def train(*args, **arguments):
        order.append("train")
        expected = candidates[0] if use_model else candidates[2]
        assert tuple(v.map_id for v in arguments["venues"]) == (expected.map_id,)
        assert arguments["venues"][0].move_guard is native.native_training_move_guard
        raise EvolutionTrainingPaused(0, 0)
    monkeypatch.setattr(context, "run_red_team_balancing", train)
    model = upgrade_party_development_model_for_workload(_initialized_model())
    digest = canonical_party_development_outcome_model_sha256(model)
    def observer(observation, venues, actual_source, actual_target):
        order.append("observer")
        assert observation.party == exact
        assert (actual_source, actual_target) == (source, target)
        assert tuple(v.map_id for v in venues) == tuple(v.map_id for v in candidates)
        if observer_fault:
            monkeypatch.setattr(type(runtime.emulator), "save_state_bytes", lambda self: b"changed")
    arguments = {"observe_venue_decision": observer}
    if use_model:
        arguments.update(venue_model=model, venue_model_sha256=digest)
    bound = native.bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"test"), **arguments)
    actions = CountingExecutor(_ActionDelegate())
    if observer_fault:
        with pytest.raises(context.RedGoalContextError, match="observer changed execution state"):
            bound.party_level_evolution_executor(source, target, actions)
        assert order == ["center", "nurse", "observer"]
        assert seen == []
    else:
        bound.party_level_evolution_executor(source, target, actions)
        assert order == ["center", "nurse", "observer"] + (["model"] if use_model else []) + ["train"]
        assert len(seen) == int(use_model)
        if seen:
            assert seen[0]["model_sha256"] == digest
    assert actions.actions_executed == runtime.emulator.frame_count == 0
