"""ROM-free checks for the distinct ordinary-K venue protocol and bindings."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_ordinary_preparation_venue as venue_module
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.party_development_rank import PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID
from pokemon_red_completion.red_living_dex_wild_corridor import RedLivingDexWildCorridor
from pokemon_red_completion.red_ordinary_preparation_venue import (
    OrdinaryPreparationVenue, OrdinaryPreparationVenuePolicy, build_ordinary_preparation_venue_menu,
)
from test_red_party_development_adapter import _observation


def venues():
    return tuple(OrdinaryPreparationVenue(RedLivingDexWildCorridor(source, int(map_id), (6, 4), (5, 4)), source, int(home))
        for source, map_id, home in (("wild:Route7:grass", MapId.ROUTE_7, MapId.CELADON_POKECENTER),
                                    ("wild:Route11:grass", MapId.ROUTE_11, MapId.VERMILION_POKECENTER)))


@pytest.fixture
def ordinary(monkeypatch):
    observation = _observation()
    members = tuple(replace(m, experience=m.level ** 3) for m in observation.party.members)
    observation = replace(observation, party=PartyObservation(members))
    choices = venues()
    tables = {choices[0].corridor.map_id: (SimpleNamespace(medium="grass", slots=((18, 0x24),) * 10),),
              choices[1].corridor.map_id: (SimpleNamespace(medium="grass", slots=((13, 0x24),) * 10),)}
    monkeypatch.setattr(venue_module, "wild_encounter_tables", lambda _: tables)
    monkeypatch.setattr(venue_module, "evolution_graph", lambda _: {})
    monkeypatch.setattr(venue_module, "RedPracticeCartridge", lambda _: SimpleNamespace(
        species=lambda _: SimpleNamespace(experience_at_level=lambda level: level ** 3)))
    return observation, choices


def build(ordinary, **kwargs):
    observation, choices = ordinary
    return build_ordinary_preparation_venue_menu(observation, rom=b"fixture", trainee=observation.party.members[0],
        target_level=23, venues=kwargs.pop("venues", choices), **kwargs)


def test_ordinary_menu_has_decoded_bands_and_truthful_unknown_yield(ordinary):
    menu = build(ordinary)
    assert menu.candidate_set.feature_schema_id == PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID
    assert menu.candidate_available == (True, True)
    assert all(not area.is_measured for area in menu.bindings)
    rows = menu.candidate_set.public_dict()["candidates"]
    for row in rows:
        f = row["features"]
        assert f["venue.useful_encounters_known"] == 0
        assert f["venue.useful_encounter_share"] == 0
        assert f["venue.expected_recipient_xp_per_encounter"] == 0
        assert f["venue.travel_steps_known"] == f["venue.recovery_steps_known"] == 0
        assert f["venue.prior_available"] == 0
        assert f["context.goal.balance"] == 1
        assert f["candidate.evolution_required"] == 0
    assert rows[0]["features"] != rows[1]["features"]
    assert (menu.bindings[0].minimum_encounter_level, menu.bindings[1].minimum_encounter_level) == (18, 13)


def test_ordinary_venue_features_are_permutation_equivariant(ordinary):
    _, choices = ordinary
    forward = build(ordinary)
    reverse = build(ordinary, venues=choices[::-1])
    assert [c.features for c in forward.candidate_set.candidates] == [c.features for c in reversed(reverse.candidate_set.candidates)]
    assert forward.semantic_snapshot_sha256 != reverse.semantic_snapshot_sha256


@pytest.mark.parametrize("target", [22, 21, 101, True])
def test_ordinary_venue_rejects_unmet_or_invalid_target(ordinary, target):
    obs, choices = ordinary
    with pytest.raises(ValueError, match="unmet legal"):
        build_ordinary_preparation_venue_menu(obs, rom=b"fixture", trainee=obs.party.members[0], target_level=target, venues=choices)


def test_ordinary_venue_rejects_duplicate_and_missing_xp(ordinary):
    obs, choices = ordinary
    with pytest.raises(ValueError, match="repeats"):
        build(ordinary, venues=(choices[0], choices[0]))
    member = replace(obs.party.members[0], experience=None)
    obs = replace(obs, party=PartyObservation((member,) + obs.party.members[1:]))
    with pytest.raises(ValueError, match="XP binding"):
        build_ordinary_preparation_venue_menu(obs, rom=b"fixture", trainee=member, target_level=23, venues=choices)


def test_ordinary_venue_projects_k_damaging_moves_not_collection_escape_protocol(ordinary, monkeypatch):
    calls = []
    original = venue_module.observe_red_venue_matchup_context
    def observe(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(venue_module, "observe_red_venue_matchup_context", observe)
    build(ordinary)
    assert len(calls) == 2
    assert all(c["collection_attack_filter"] is False for c in calls)
    assert all("escaped_species" not in c for c in calls)


@pytest.mark.parametrize("single_venue", [False, True])
@pytest.mark.parametrize("task_contract", ["native-level-dose-v1", "party-development.fixed-level-ready-task-cost.v1"])
def test_batched_ordinary_binding_preserves_member_target_and_executes_selected_venue(monkeypatch, single_venue, task_contract):
    import pokemon_red_completion.red_player_member_preparation as module
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.party_preparation import build_preparation_plan
    from test_red_player_member_preparation import roster
    from test_party_preparation import enemies
    from test_red_live_option_menu import _binding
    members = roster()
    plan = build_preparation_plan(members, enemies(18, 21))
    monkeypatch.setattr(module, "observe_preparation_members", lambda *_: members)
    monkeypatch.setattr(module, "internal_to_dex", lambda _: {i: i for i in range(1, 5)})
    monkeypatch.setattr(module, "evolution_graph", lambda _: {})
    monkeypatch.setattr(module, "RedPracticeCartridge", lambda _: SimpleNamespace(
        species=lambda _: SimpleNamespace(experience_at_level=lambda n: n ** 3)))
    monkeypatch.setattr(venue_module, "validate_native_evolution_venue_model", lambda *_: None)
    import pokemon_red_completion.red_native_venue_geometry as geometry
    monkeypatch.setattr(geometry, "quote_ordinary_preparation_venue_geometry", lambda _runtime, _route, vs: (None,) * len(vs))
    predictions = []
    model = SimpleNamespace(feature_schema_id=PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID,
        predict=lambda candidates: predictions.append(candidates) or 1)
    policy = OrdinaryPreparationVenuePolicy(model, "a" * 64, task_contract)
    candidate_set = SimpleNamespace(public_dict=lambda: {"fixture": True})
    monkeypatch.setattr(venue_module, "build_ordinary_preparation_venue_menu", lambda *_args, **kwargs:
        SimpleNamespace(candidate_set=candidate_set, semantic_snapshot_sha256="b" * 64))
    bound, executed, records = [], [], []
    def routed(*_args, **kwargs):
        assert callable(kwargs["record"]), "selected child must retain the existing recorder"
        assert kwargs.get("restore_completed_target", False) is (
            task_contract == "party-development.fixed-level-ready-task-cost.v1"
        )
        target, corridor = kwargs["plan"].targets[0], kwargs["corridor"]
        bound.append((target, corridor.map_id))
        binding = _binding(GoalKind.DEVELOP_TEAM, binding_ref="same-origin-home", calls=[])
        def execute():
            executed.append((target, corridor.map_id))
            return binding.execute()
        return replace(binding, execute=execute)
    monkeypatch.setattr(module, "routed_preparation_binding", routed)
    emulator = SimpleNamespace(save_state_bytes=lambda: b"same", frame_count=0, pressed_buttons=frozenset())
    runtime = SimpleNamespace(emulator=emulator, adapter=SimpleNamespace(observe=lambda: _observation()))
    choices = venues()[:1] if single_venue else venues()
    rows = module.learned_member_preparation_options(runtime, SimpleNamespace(actions_executed=0), plan=plan,
        opponent_levels=(18, 21), forecast_ref="preview", route=SimpleNamespace(rom=b"fixture"),
        venues=choices, battler_for_map=lambda _: SimpleNamespace(), venue_policy=policy,
        maximum_level_gains=(1,), record=lambda *args: records.append(args))
    assert len(rows) == len(records) == 4
    assert len(predictions) == (0 if single_venue else 4)
    assert all(rec[1]["model_selected"] is (not single_venue) for rec in records)
    assert len(bound) == (4 if single_venue else 8) and not executed
    assert len({b.binding_ref for b, _ in rows}) == 4
    for b, descriptor in rows:
        assert descriptor.target_level == descriptor.current_level + 1
        b.execute()
    assert all(map_id == choices[0 if single_venue else 1].corridor.map_id for _, map_id in executed)
    assert {target for target, _ in executed} == {target for target, _ in bound}
    assert plan.roster == members
@pytest.fixture
def ordinary_model_record(tmp_path):
    import json
    from hashlib import sha256
    from test_party_development_outcome_learning import _initialized_model
    from pokemon_red_completion.party_development_outcome_learning import (
        upgrade_party_development_model_for_workload, upgrade_party_development_model_for_matchups,
        canonical_party_development_outcome_model_sha256,
    )
    model = upgrade_party_development_model_for_matchups(upgrade_party_development_model_for_workload(_initialized_model()))
    path = tmp_path / "ordinary-initializer.json"
    path.write_text(json.dumps(model.to_dict(), sort_keys=True))
    spec = dict(path=str(path), content_sha256=sha256(path.read_bytes()).hexdigest(),
        model_sha256=canonical_party_development_outcome_model_sha256(model),
        scope="all-existing-legal-ordinary-preparation-venues", reason="ROM-free opt-in fixture; unqualified initializer")
    return dict(partition="train", ordinary_preparation_venue_model=spec)


def test_ordinary_declaration_is_separate_pinned_opt_in(ordinary_model_record):
    from pokemon_red_completion.red_player_configuration import declared_ordinary_preparation_venue_policy
    assert declared_ordinary_preparation_venue_policy({}) is None
    assert declared_ordinary_preparation_venue_policy(dict(native_evolution_venue_model={})) is None
    policy = declared_ordinary_preparation_venue_policy(ordinary_model_record)
    assert policy.model_sha256 == ordinary_model_record["ordinary_preparation_venue_model"]["model_sha256"]
    assert policy.model.outcome_training_examples == 0


@pytest.mark.parametrize("field,value", [
    ("partition", "benchmark"), ("partition", "actual"),
    ("scope", "route11"), ("model_sha256", "b" * 64),
    ("content_sha256", "b" * 64), ("reason", ""), ("path", "relative.json"),
])
def test_ordinary_declaration_rejects_wrong_scope_identity_or_partition(ordinary_model_record, field, value):
    from pokemon_red_completion.red_player_configuration import declared_ordinary_preparation_venue_policy
    plan = ordinary_model_record
    if field == "partition":
        plan[field] = value
    else:
        plan["ordinary_preparation_venue_model"][field] = value
    with pytest.raises(ValueError):
        declared_ordinary_preparation_venue_policy(plan)

def test_ordinary_geometry_is_independent_of_unknown_k_yield_and_home_bound(ordinary):
    from pokemon_red_completion.red_native_venue_geometry import NativeVenueGeometryQuote
    obs, vs = ordinary
    qs = tuple(NativeVenueGeometryQuote((v.source_id, ()), obs.raw, 18 + i, 9 + i,
        (v.corridor.map_id, v.corridor.origin_at), 0, (), ordinary_home_map=v.home_map) for i, v in enumerate(vs))
    menu = build(ordinary, geometry_quotes=qs)
    rows = menu.candidate_set.public_dict()["candidates"]
    for i, row in enumerate(rows):
        f = row["features"]
        assert f["venue.useful_encounters_known"] == 0
        assert f["venue.travel_steps_known"] == f["venue.recovery_steps_known"] == 1
        assert f["venue.travel_steps"] == (18 + i) / 1_000_000
        assert f["venue.recovery_steps"] == (9 + i) / 1_000_000
    wrong = (replace(qs[0], ordinary_home_map=vs[1].home_map), qs[1])
    with pytest.raises(ValueError, match="home differs"):
        build(ordinary, geometry_quotes=wrong)


@pytest.mark.parametrize("missing_return", [False, True])
def test_ordinary_geometry_reuses_source_home_outbound_and_canonical_return(monkeypatch, missing_return):
    import pokemon_red_completion.red_native_venue_geometry as geometry
    import pokemon_red_completion.red_living_dex_provider_plan as provider
    from pokemon_red_completion.route_plan import RoutePlanningError
    obs, vs = _observation(), venues()
    raw, calls = obs.raw, []
    start = SimpleNamespace(map_id=raw.map_id, at=(raw.player_y, raw.player_x))
    monkeypatch.setattr(geometry, "Gen1TraversalObserver", lambda *_a, **_k: SimpleNamespace(observe=lambda: start))
    monkeypatch.setattr(geometry, "ground_route_capability_projector", lambda *_: None)
    monkeypatch.setattr(provider, "red_living_dex_route_terminal_snapshot", lambda _world, _start, p: SimpleNamespace(map_id=p.terminal_map, at=p.terminal_at))
    def plan(origin, destination, *, goal_at):
        calls.append((origin.map_id, destination, goal_at))
        phase = (len(calls) - 1) % 3
        if phase == 2 and missing_return:
            raise RoutePlanningError("no return proof")
        return SimpleNamespace(steps=(None,) * (11, 7, 5)[phase], terminal_map=destination, terminal_at=goal_at)
    em = SimpleNamespace(save_state_bytes=lambda: b"same", frame_count=0, pressed_buttons=frozenset())
    rt = SimpleNamespace(reader=SimpleNamespace(read=lambda: raw), emulator=em)
    quotes = geometry.quote_ordinary_preparation_venue_geometry(rt, SimpleNamespace(route_world=SimpleNamespace(plan_feasible_to_map=plan)), vs)
    assert len(calls) == 6
    assert [q.travel_steps for q in quotes] == [18, 18]
    assert [q.recovery_steps for q in quotes] == ([None, None] if missing_return else [5, 5])
    for v, q in zip(vs, quotes):
        assert q.ordinary_home_map == v.home_map
        assert q.planned_entry == (v.corridor.map_id, v.corridor.origin_at)
        assert q.flight_count == 0
    assert calls[:3] == [(raw.map_id, vs[0].home_map, (3, 3)),
        (vs[0].home_map, vs[0].corridor.map_id, vs[0].corridor.origin_at),
        (vs[0].corridor.map_id, vs[0].home_map, (3, 3))]

def test_ordinary_policy_cannot_silently_use_single_map_train_admission(ordinary_model_record, tmp_path):
    import json
    from test_red_player_configuration import config
    from pokemon_red_completion.red_player_configuration import assemble_configured_player
    path = tmp_path / "work.json"
    path.write_text(json.dumps(ordinary_model_record))
    backend = SimpleNamespace(assembly=lambda *_a, **_k: pytest.fail("narrowed policy reached backend"))
    with pytest.raises(ValueError, match="single-map"):
        assemble_configured_player(backend, config(), tmp_path, tmp_path,
            plan_path=path, model_feature_version=16, training_admission=object())

@pytest.mark.parametrize("value", [None, True, {}, "unknown-task-v1"])
def test_ordinary_ready_contract_rejects_unknown_or_coerced_values_before_model_read(ordinary_model_record,monkeypatch,value):
    import pokemon_red_completion.party_development_outcome_learning as learning
    from pokemon_red_completion.red_player_configuration import declared_ordinary_preparation_venue_policy
    ordinary_model_record["ordinary_preparation_venue_model"]["task_contract"]=value
    monkeypatch.setattr(learning,"load_party_development_outcome_model",lambda *a,**k:pytest.fail("invalid task must fail before model read"))
    with pytest.raises(ValueError,match="ordinary venue policy"):
        declared_ordinary_preparation_venue_policy(ordinary_model_record)

def test_ordinary_fixed_ready_declaration_binds_the_task_without_changing_model_identity(ordinary_model_record):
    from pokemon_red_completion.red_player_configuration import declared_ordinary_preparation_venue_policy
    spec=ordinary_model_record["ordinary_preparation_venue_model"]
    old=declared_ordinary_preparation_venue_policy(ordinary_model_record)
    spec["task_contract"]="party-development.fixed-level-ready-task-cost.v1"
    ready=declared_ordinary_preparation_venue_policy(ordinary_model_record)
    assert old.model_sha256==ready.model_sha256
    assert old.task_contract=="native-level-dose-v1"
    assert ready.task_contract==spec["task_contract"]
