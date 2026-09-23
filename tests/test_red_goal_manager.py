from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalNeed,
    GoalUnavailableReason,
)
from pokemon_red_completion.objective_skills import (
    ObjectiveSkillAvailability,
    ObjectiveSkillError,
    ObjectiveSkillExecution,
    ObjectiveSkillRegistry,
)
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalOpportunityEnumerator,
    RedStoryGoalBindingProvider,
)


def _graph() -> QuestGraph:
    return QuestGraph(
        (
            Objective(
                "first",
                "First",
                frozenset({"story:first"}),
                Specialist.INTERACTION,
                priority=0,
            ),
            Objective(
                "second",
                "Second",
                frozenset({"story:second"}),
                Specialist.BATTLE,
                prerequisites=frozenset({"first"}),
                priority=1,
            ),
        )
    )


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=1,
        player_x=2,
        player_y=3,
        party_count=1,
        battle_state=0,
        bag_item_ids=(int(ItemId.POKE_BALL), int(ItemId.POTION)),
        bag_items=((int(ItemId.POKE_BALL), 5), (int(ItemId.POTION), 2)),
        party_species_ids=(0x1C,),
        party_levels=(55,),
        party_hp=(150,),
        party_max_hp=(180,),
        party_status=(0,),
        party_moves=((57, 58, 55, 0),),
        party_pp=((15, 10, 5, 0),),
    )


class _Reader:
    def __init__(self) -> None:
        self.raw = _raw()

    def read(self) -> RawGameState:
        return self.raw

    def read_pokedex_state(self) -> RedPokedexState:
        return RedPokedexState(frozenset({9}), frozenset({9}))

    def read_all_box_states(self) -> RedBoxCollectionState:
        return RedBoxCollectionState(
            tuple(RedCurrentBoxState(index, (), ()) for index in range(12)),
            current_box_index=0,
            storage_initialized=False,
        )

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0, 0, 0, 0, 0)


class _Observer:
    def __init__(self) -> None:
        self.state = GameState(
            GameMode.OVERWORLD,
            frozenset({"story:first"}),
            "test_boundary",
        )

    def observe_raw(self, _raw: RawGameState) -> GameState:
        return self.state

    def observe(self) -> GameState:
        return self.state


def test_red_adapter_composes_story_collection_party_resources_and_storage() -> None:
    observer = _Observer()
    observed = PokemonRedGoalStateAdapter(_Reader(), observer, _graph()).observe()

    legacy = observed.public_dict()
    assert observed.economy_snapshot() is None  # fixture has no observed money
    funded = replace(observed, raw=replace(observed.raw, player_money=593))
    assert funded.economy_snapshot().cash == 593
    assert funded.public_dict() == legacy  # prospective seam does not relabel history

    assert observed.party.species_ids() == (0x1C,)
    assert observed.evidence.story.completed == 1
    assert observed.evidence.story.target == 2
    assert observed.evidence.registered_collection.completed == 1
    assert observed.evidence.living_collection.completed == 1
    assert observed.evidence.level_collection.completed == 0
    assert observed.capture_item_count == 5
    assert observed.recovery_item_count == 2
    assert observed.free_storage_slots == 240
    assert observed.immediate_capture_slots == 25
    assert observed.situation.pressure(GoalNeed.COLLECTION_PROGRESS) == pytest.approx(
        1.0
        - min(
            observed.evidence.registered_collection.satisfaction,
            observed.evidence.living_collection.satisfaction,
        )
    )
    assert observed.situation.pressure(GoalNeed.CONTROL_RECOVERY) == 0.0
    assert observed.public_dict()["raw_address_fields"] == 0


def test_red_adapter_storage_pressure_tracks_active_capture_capacity() -> None:
    reader = _Reader()
    raw = reader.raw
    reader.raw = replace(
        raw,
        party_count=6,
        party_species_ids=raw.party_species_ids * 6,
        party_levels=raw.party_levels * 6,
        party_hp=raw.party_hp * 6,
        party_max_hp=raw.party_max_hp * 6,
        party_status=raw.party_status * 6,
        party_moves=raw.party_moves * 6,
        party_pp=raw.party_pp * 6,
    )

    def full_active_box() -> RedBoxCollectionState:
        boxes = [RedCurrentBoxState(index, (), ()) for index in range(12)]
        boxes[0] = RedCurrentBoxState(0, (0x1C,) * 20, (55,) * 20)
        return RedBoxCollectionState(tuple(boxes), 0, True)

    reader.read_all_box_states = full_active_box  # type: ignore[method-assign]
    observed = PokemonRedGoalStateAdapter(reader, _Observer(), _graph()).observe()

    assert observed.free_storage_slots == 220
    assert observed.immediate_capture_slots == 0
    assert observed.situation.pressure(GoalNeed.STORAGE_CAPACITY) == 1.0


@dataclass
class _Skill:
    observer: _Observer
    objective_id: str = "second"
    specialist: Specialist = Specialist.BATTLE
    expected_facts: frozenset[str] = frozenset({"story:second"})
    additional_effect_facts: frozenset[str] = frozenset()
    max_actions: int = 20
    max_frames: int = 2_000

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        return ObjectiveSkillAvailability(
            "story:first" in state.facts and "story:second" not in state.facts,
            "at the bounded second-objective boundary",
        )

    def execute(self) -> ObjectiveSkillExecution:
        self.observer.state = self.observer.state.with_facts("story:second")
        return ObjectiveSkillExecution(4, 400, {"verified": True})


@dataclass
class _BranchSkill(_Skill):
    blocked: bool = False
    calls: int = 0

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        return ObjectiveSkillAvailability(
            not self.blocked and not self.expected_facts.issubset(state.facts), "branch boundary",
        )

    def execute(self) -> ObjectiveSkillExecution:
        self.calls += 1
        self.observer.state = self.observer.state.with_facts(*self.expected_facts)
        return ObjectiveSkillExecution(4, 400, {"verified": True})


def _branches(names=("second", "third"), reverse=False):
    observer = _Observer()
    branches = tuple(
        Objective(name, name, frozenset({f"story:{name}"}), specialist,
                  prerequisites=frozenset({"first"}), priority=index + 1)
        for index, (name, specialist) in enumerate(zip(
            names, (Specialist.BATTLE, Specialist.NAVIGATION), strict=True,
        ))
    )
    graph = QuestGraph((tuple(_graph())[0], *branches))
    skills = tuple(_BranchSkill(
        observer, objective_id=obj.id, specialist=obj.specialist,
        expected_facts=obj.completion_facts, max_actions=(index + 1) * 20,
    ) for index, obj in enumerate(branches))
    provider = RedStoryGoalBindingProvider(
        graph, ObjectiveSkillRegistry(skills[::-1] if reverse else skills), observer,
    )
    observation = PokemonRedGoalStateAdapter(_Reader(), observer, graph).observe()
    return observer, observation, provider, skills


@pytest.mark.parametrize("names", [("second", "third"), ("west", "east")])
@pytest.mark.parametrize("reverse", [False, True])
def test_plural_story_bindings_execute_only_selected_branch(names, reverse):
    observer, observation, provider, skills = _branches(names, reverse)
    offers = provider.offers(observation)
    assert [o.binding.binding_ref for o in offers] == [
        f"pokemon.red:story:{name}" for name in names
    ]
    assert [skill.calls for skill in skills] == [0, 0]
    assert provider.offer(observation).binding.binding_ref == offers[0].binding.binding_ref
    execution = offers[1].binding.execute()
    assert offers[1].binding.verify(execution).status.value == "succeeded"
    assert offers[0].binding.verify(execution).status.value == "failed"
    assert [skill.calls for skill in skills] == [0, 1]
    assert f"story:{names[1]}" in observer.state.facts
    # Completing one branch leaves the other, rather than an unavailable placeholder.
    assert len(provider.offers(replace(observation, game_state=observer.state))) == 1
    observer.state = GameState(GameMode.OVERWORLD, skills[1].expected_facts, "boundary")
    assert offers[1].binding.verify(execution).status.value == "failed"  # lost prerequisite


def test_plural_story_bindings_mask_prerequisites_availability_and_missing_capabilities():
    observer, observation, provider, skills = _branches()
    skills[0].blocked = True
    assert len(provider.offers(observation)) == 1
    skills[1].blocked = True
    assert provider.offers(observation) == ()
    assert (provider.offer(observation).unavailable_reason
            is GoalUnavailableReason.TEMPORARILY_BLOCKED)
    missing = replace(provider, skills=ObjectiveSkillRegistry())
    assert missing.offers(observation) == ()
    assert missing.offer(observation).unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    unstarted = replace(observation, game_state=GameState(GameMode.OVERWORLD, frozenset()))
    assert provider.offers(unstarted) == ()
    skills[0].blocked = False
    skills[0].expected_facts = frozenset({"story:wrong"})
    with pytest.raises(ObjectiveSkillError, match="contract"):
        provider.offers(observation)
    with pytest.raises(TypeError):
        provider.offers(None)


def test_plural_story_candidates_are_identity_free_and_non_equivalent():
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
    from pokemon_red_completion.red_live_option_menu import (
        build_red_live_option_set,
        supplemental_live_option,
    )

    menus = []
    for names, reverse in ((('second', 'third'), False), (('west', 'east'), True)):
        _, observation, provider, _ = _branches(names, reverse)
        observation = replace(observation, raw=replace(observation.raw, player_money=7511))
        empty = RedGoalOpportunityEnumerator(()).enumerate(observation)
        supplements = []
        for offer in provider.offers(observation):
            binding = offer.binding
            opportunities = (binding.opportunity, *(o for o in empty.opportunities
                                                    if o.kind is not binding.kind))
            question = GoalBindingSet(opportunities, (binding,)).question(observation.situation)
            candidate = project_living_dex_goal_candidate(
                question, 0, feature_version=4, binding_ref=binding.binding_ref,
            )
            supplements.append(supplemental_live_option(binding, candidate))
        options = build_red_live_option_set(
            situation=observation.situation, binding_set=empty, supplements=tuple(supplements),
            model_feature_version=4, ordering_seed_sha256="a" * 64,
            economy_snapshot=observation.economy_snapshot(), target_cash=2300,
        )
        menus.append(options.menu)
    assert len(menus[0].available_indices) == 2
    first = tuple(c.features for c in menus[0].candidates)
    second = tuple(c.features for c in menus[1].candidates)
    assert first == second
    assert first[0] != first[1]


def test_red_enumerator_hard_masks_missing_skills_and_binds_story() -> None:
    observer = _Observer()
    observation = PokemonRedGoalStateAdapter(_Reader(), observer, _graph()).observe()
    provider = RedStoryGoalBindingProvider(
        _graph(),
        ObjectiveSkillRegistry((_Skill(observer),)),
        observer,
    )

    bindings = RedGoalOpportunityEnumerator((provider,)).enumerate(observation)

    assert len(bindings.opportunities) == len(GoalKind) == 9
    story = next(item for item in bindings.opportunities if item.kind is GoalKind.ADVANCE_STORY)
    acquire = next(
        item for item in bindings.opportunities if item.kind is GoalKind.ACQUIRE_SPECIES
    )
    assert story.availability is GoalAvailability.AVAILABLE
    assert acquire.availability is GoalAvailability.UNAVAILABLE
    assert acquire.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert len(bindings.bindings) == 1

    execution = bindings.bindings[0].execute()
    verification = bindings.bindings[0].verify(execution)

    assert execution.actions_executed == 4
    assert verification.status.value == "succeeded"
