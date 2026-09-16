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


@pytest.mark.parametrize("routed", (False, True))
@pytest.mark.parametrize("blocked", (None, "registered", "protected", "route", "max_level"))
def test_level_alternatives_bind_real_stock_and_preserve_selected_executor(
    tmp_path, monkeypatch, routed, blocked,
):
    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
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

    def bind(actual, world, **kwargs):
        assert kwargs == {"maximum_quanta": 128, "allow_cross_box": True}
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


@pytest.mark.parametrize("party_copies", (1, 2))
def test_in_party_level_continuation_uses_trainee_level_and_unique_source(
    tmp_path, monkeypatch, party_copies,
):
    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
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
