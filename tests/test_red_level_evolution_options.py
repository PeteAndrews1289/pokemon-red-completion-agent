from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context import _ActionDelegate
from test_red_live_option_menu import _binding
from test_red_native_boxed_item_evolution import _runtime

import pokemon_red_completion.red_level_evolution_options as module
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.observation import ItemId, RedCurrentBoxState
from pokemon_red_completion.red_collection import red_internal_species_id, red_species_ref
from pokemon_red_completion.red_goal_context import DIGLETTS_CAVE_TRAINING_VENUE
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)


@pytest.mark.parametrize("current,target,progress,remaining", [
    (19, 20, None, 1), (19, 20, 0., 1), (19, 20, .99, .01),
    (19, 36, .5, 16.5), (30, 28, .75, .25), (99, 100, 1., 0.),
])
def test_level_workload_uses_observed_xp_not_identity(current, target, progress, remaining):
    assert module.level_evolution_effort(current, target, progress) == pytest.approx(remaining / 99)


@pytest.mark.parametrize("progress", [-.1, 1.1, float("nan")])
def test_level_workload_rejects_invalid_progress(progress):
    with pytest.raises(ValueError, match="unit fraction"):
        module.level_evolution_effort(19, 20, progress)


@pytest.mark.parametrize("routed", (False, True))
@pytest.mark.parametrize("blocked", (None, "registered", "protected", "route", "max_level"))
@pytest.mark.parametrize("declared", (False, True))
@pytest.mark.parametrize("optimized", (False, True))
@pytest.mark.parametrize("venue_override", (False, True))
def test_level_alternatives_bind_real_stock_and_preserve_selected_executor(
    tmp_path, monkeypatch, routed, blocked, declared, optimized, venue_override,
):
    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    monkeypatch.setattr(module, "RedPracticeCartridge", lambda rom: object())
    monkeypatch.setattr(module.PokemonRedPartyReader, "read_with_level_progress",
                        lambda self, cartridge: runtime.adapter.observe().party)
    if not declared:
        providers = {
            spec.kind: (spec.kind, spec.mechanic, dict(spec.parameters))
            for spec in runtime.profile.providers if spec.kind is not GoalKind.EVOLVE_SPECIES
        }
        providers[GoalKind.ADVANCE_STORY] = (
            GoalKind.ADVANCE_STORY, RedGoalMechanic.OAKS_ERRAND, {})
        providers[GoalKind.RECOVER_CONTROL] = (
            GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {})
        runtime = replace(runtime, profile=parse_red_goal_context_profile(
            build_red_goal_context_profile_payload(profile_id=runtime.profile.profile_id,
                providers=tuple(providers[kind] for kind in GoalKind if kind in providers))))
    original_profile = runtime.profile
    reader.boxes = replace(reader.boxes, boxes=(
        RedCurrentBoxState(0, (red_internal_species_id(98),),
                           (100 if blocked == "max_level" else 30,)),
        RedCurrentBoxState(1, (red_internal_species_id(104),), (19,)),
        *reader.boxes.boxes[2:],
    ))
    owned = reader.read_pokedex_state().owned_species | {98, 104}
    reader.read_pokedex_state = lambda: SimpleNamespace(seen_species=owned, owned_species=owned)
    observation = runtime.adapter.observe()
    if blocked == "registered":
        observation = replace(observation, collection_observation=replace(
            observation.collection_observation,
            owned_species=observation.collection_observation.owned_species | {red_species_ref(99)},
        ))
    # Both are canonical catches, but the cartridge also permits these evolutions.
    monkeypatch.setattr(module, "evolution_graph", lambda _: {
        98: (Evolution(98, 99, EvolutionMethod.LEVEL, 28),),
        104: (Evolution(104, 105, EvolutionMethod.LEVEL, 28),),
        118: (Evolution(118, 119, EvolutionMethod.LEVEL, 33),),  # No local specimen.
    })
    calls, offered_targets = [], []
    def wrapper(inner, spec):
        return inner

    def bind(actual, world, **kwargs):
        assert callable(actual.evolution_stop_requested)
        assert actual.evolution_stop_requested() is False
        assert runtime.evolution_stop_requested is None
        expected = {"maximum_quanta": 128, "allow_cross_box": True}
        if optimized:
            expected.update(prefer_highest_supported_venue=True, allow_guarded_venue_escapes=True)
        if venue_override:
            expected["training_venues"] = (DIGLETTS_CAVE_TRAINING_VENUE,)
        assert kwargs == expected
        spec = next(s for s in actual.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)
        source = spec.parameters["source_species_ref"]
        target = spec.parameters["target_species_ref"]
        offered_targets.append(target)
        allowed = actual.registration_policy.evolution_allowed(
            observation.collection_observation, source, target,
        )
        if blocked == "protected" and source == red_species_ref(98):
            allowed = False  # Preserve the native provider's stock rejection.
        binding = _binding(GoalKind.EVOLVE_SPECIES, binding_ref="private:" + target, calls=calls)
        reason = (GoalUnavailableReason.NO_LEGAL_TARGET if not allowed
                  else GoalUnavailableReason.MISSING_CAPABILITY if routed else None)
        return SimpleNamespace(
            binding=binding, allowed=allowed,
            provider_for=lambda *a: SimpleNamespace(offer=lambda _: SimpleNamespace(
                binding=binding if reason is None else None, unavailable_reason=reason,
            )),
        )

    def router(native, actions, world, **kwargs):
        assert kwargs["maximum_controller_actions"] == 3000
        assert kwargs["maximum_emulator_frames"] == 300000
        assert kwargs.get("interruption_handler_wrapper") is wrapper
        return SimpleNamespace(enumerate_routed_kinds=lambda obs, kinds: SimpleNamespace(
            bindings=() if blocked == "route" else (native.binding,),
        ))

    monkeypatch.setattr(module, "bind_native_boxed_evolution", bind)
    monkeypatch.setattr(module, "RedResourceGoalRouter", router)
    actions = CountingExecutor(_ActionDelegate())
    before = reader.read(), runtime.emulator.frame_count
    candidates = module.enumerate_red_level_evolutions(
        runtime, observation, actions, SimpleNamespace(rom=b"fixture"),
        maximum_actions=3000, maximum_frames=300000,
        prefer_highest_supported_venue=optimized, allow_guarded_venue_escapes=optimized,
        training_venues=(DIGLETTS_CAVE_TRAINING_VENUE,) if venue_override else None,
        interruption_handler_wrapper=wrapper,
    )
    targets = (105,) if blocked in {"protected", "registered", "max_level"} else (99, 105)
    expected = set() if blocked == "route" and routed else {red_species_ref(n) for n in targets}
    assert {c.binding.binding_ref.removeprefix("private:") for c in candidates} == expected
    assert red_species_ref(119) not in offered_targets
    for candidate in candidates:
        target = candidate.binding.binding_ref.removeprefix("private:")
        assert candidate.execution_effort == (1 if target == red_species_ref(99) else 9) / 99
        assert candidate.economy_offer.planned_spend == 0
        candidate.binding.execute()
        assert calls[-1] == candidate.binding.binding_ref
    assert before == (reader.read(), runtime.emulator.frame_count)
    assert actions.actions_executed == 0
    assert runtime.profile == original_profile
    assert any(s.kind is GoalKind.EVOLVE_SPECIES for s in runtime.profile.providers) is declared


@pytest.mark.parametrize("venues", [[], (), (object(),),
                                  (DIGLETTS_CAVE_TRAINING_VENUE,) * 2])
def test_declared_evolution_venues_refuse_before_live_access(venues):
    with pytest.raises(ValueError, match="distinct declared"):
        module.enumerate_red_level_evolutions(
            None, None, None, None, maximum_actions=1, maximum_frames=1,
            training_venues=venues,
        )


@pytest.mark.parametrize('wrapper', [True, 3, object()])
def test_invalid_evolution_wrapper_refuses_before_live_access(wrapper):
    with pytest.raises(TypeError, match='evolution interruption wrapper must be callable'):
        module.enumerate_red_level_evolutions(
            None, None, None, None, maximum_actions=1, maximum_frames=1,
            interruption_handler_wrapper=wrapper,
        )


@pytest.mark.parametrize("party_copies", (1, 2))
def test_in_party_level_continuation_uses_trainee_level_and_unique_source(
    tmp_path, monkeypatch, party_copies,
):
    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    monkeypatch.setattr(module, "RedPracticeCartridge", lambda rom: object())
    monkeypatch.setattr(module.PokemonRedPartyReader, "read_with_level_progress",
                        lambda self, cartridge: runtime.adapter.observe().party)
    source = red_internal_species_id(98)
    reader.boxes = replace(reader.boxes, boxes=(
        RedCurrentBoxState(0, (source,), (15,)),
        *reader.boxes.boxes[1:],
    ))
    party = list(reader.raw.party_species_ids)
    levels = list(reader.raw.party_levels)
    for index in range(party_copies):
        party[index], levels[index] = source, 16
    reader.raw = replace(reader.raw, party_species_ids=tuple(party), party_levels=tuple(levels))
    owned = reader.read_pokedex_state().owned_species | {98}
    reader.read_pokedex_state = lambda: SimpleNamespace(seen_species=owned, owned_species=owned)
    observation = runtime.adapter.observe()
    monkeypatch.setattr(module, "evolution_graph", lambda _: {
        98: (Evolution(98, 99, EvolutionMethod.LEVEL, 28),),
    })
    seen = []

    def bind(actual, world, **kwargs):
        assert kwargs == {"maximum_quanta": 128, "allow_cross_box": True}
        seen.append(actual.registration_policy.evolution_allowed(
            observation.collection_observation, red_species_ref(98), red_species_ref(99),
        ))
        return SimpleNamespace(provider_for=lambda *args: SimpleNamespace(
            offer=lambda _: SimpleNamespace(
                binding=_binding(GoalKind.EVOLVE_SPECIES, binding_ref="resume", calls=[]),
                unavailable_reason=None,
            ),
        ))

    monkeypatch.setattr(module, "bind_native_boxed_evolution", bind)
    actions = CountingExecutor(_ActionDelegate())
    before = reader.read(), runtime.emulator.frame_count
    found = module.enumerate_red_level_evolutions(
        runtime, observation, actions, SimpleNamespace(rom=b"fixture"),
        maximum_actions=3000, maximum_frames=300000,
    )
    assert len(found) == (1 if party_copies == 1 else 0)
    if found:
        assert found[0].execution_effort == 12 / 99
    assert seen == ([True] if party_copies == 1 else [])
    assert before == (reader.read(), runtime.emulator.frame_count)
    assert actions.actions_executed == 0


@pytest.mark.parametrize("with_workload", (False, True))
@pytest.mark.parametrize("current_box", (0, 1, 2))
@pytest.mark.parametrize("trainee_level", (27, 30))
@pytest.mark.parametrize("identity_fault", (None, "species", "level", "missing", "duplicate", "xp", "xp_before_level"))
def test_boxed_workload_quotes_exact_selected_precursor_xp_without_inputs(
    tmp_path, monkeypatch, current_box, trainee_level, identity_fault, with_workload,
):
    from pokemon_red_completion.observation import RedBoxSpecimenIdentity
    from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeSpecies

    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    source = red_internal_species_id(98)
    species = RedPracticeSpecies(source, 98, (0, 0), (30, 30, 30, 30, 30),
        100, 100, 0, (1,), (), (), b"FIXTURE")
    floor, ceiling = (species.experience_at_level(level) for level in (trainee_level, trainee_level + 1))
    selected_box = 1 if current_box == 1 else 0
    progress = (100 if selected_box == 0 else ceiling - floor - 1) / (ceiling - floor)
    identities = [
        RedBoxSpecimenIdentity(0, 1, source, trainee_level, floor + 100, 1, (0, 0)),
        RedBoxSpecimenIdentity(1, 1, source, trainee_level, ceiling - 1, 2, (0, 0)),
    ]
    if identity_fault == "species":
        identities[selected_box] = replace(identities[selected_box], species_id=source + 1)
    elif identity_fault == "level":
        identities[selected_box] = replace(identities[selected_box], level=trainee_level - 1)
    elif identity_fault == "missing":
        identities.pop(selected_box)
    elif identity_fault == "duplicate":
        identities.append(identities[selected_box])
    elif identity_fault == "xp_before_level":
        identities[selected_box] = replace(identities[selected_box], experience=floor - 1)
    elif identity_fault == "xp":
        identities[selected_box] = replace(identities[selected_box], experience=ceiling + 1)
    reads = []
    def read_identities():
        reads.append(True)
        return tuple(identities)
    reader.read_box_specimen_identities = read_identities
    reader.boxes = replace(reader.boxes, current_box_index=current_box, boxes=(
        RedCurrentBoxState(0, (source,), (trainee_level,)),
        RedCurrentBoxState(1, (source,), (trainee_level,)),
        *reader.boxes.boxes[2:],
    ))
    owned = reader.read_pokedex_state().owned_species | {98}
    reader.read_pokedex_state = lambda: SimpleNamespace(seen_species=owned, owned_species=owned)
    monkeypatch.setattr(module, "RedPracticeCartridge", lambda rom: SimpleNamespace(
        species=lambda observed: species if observed == source else pytest.fail("wrong source")))
    monkeypatch.setattr(module, "evolution_graph", lambda rom: {
        98: (Evolution(98, 99, EvolutionMethod.LEVEL, 28),),
    })
    calls = []
    binding = _binding(GoalKind.EVOLVE_SPECIES, binding_ref="observed-evolution", calls=calls)
    monkeypatch.setattr(module, "bind_native_boxed_evolution", lambda *a, **kw: SimpleNamespace(
        provider_for=lambda *a: SimpleNamespace(offer=lambda observation: SimpleNamespace(
            binding=binding, unavailable_reason=None))))
    actions = CountingExecutor(_ActionDelegate())
    before = reader.read(), dict(vars(runtime.emulator))
    def enumerate_now():
        return module.enumerate_red_level_evolutions(
            runtime, runtime.adapter.observe(), actions, SimpleNamespace(rom=b"fixture"),
            maximum_actions=3000, maximum_frames=300000, include_level_workload=with_workload)
    if identity_fault is not None:
        with pytest.raises(ValueError, match="boxed.*(identity|experience)"):
            enumerate_now()
    else:
        found = enumerate_now()
        assert len(found) == 1
        assert found[0].binding is binding
        assert found[0].execution_effort == pytest.approx((1 - progress) / 99)
        if with_workload:
            workload = found[0].level_workload
            assert workload.current_level == trainee_level
            assert workload.target_level == max(trainee_level + 1, 28)
            assert workload.remaining_xp == (species.experience_at_level(workload.target_level)
                                              - identities[selected_box].experience)
        else:
            assert found[0].level_workload is None
    assert reads == [True]
    assert before == (reader.read(), dict(vars(runtime.emulator)))
    assert actions.actions_executed == 0
    assert calls == []
