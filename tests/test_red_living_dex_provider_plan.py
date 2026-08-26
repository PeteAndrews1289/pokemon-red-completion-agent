from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion import red_living_dex_provider_plan as provider_plan
from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.global_router import (
    MacroEdge,
    MacroGraph,
    MacroPath,
    MacroTransition,
)
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import (
    red_internal_species_id,
    red_species_ref,
)
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    map_id_for_wild_source,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
    RedLivingDexProviderPlanError,
    RedLivingDexProviderRootFacts,
    freeze_red_living_dex_provider_plan,
    red_living_dex_route_terminal_snapshot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupExecutionIdentity,
    RedLivingDexSetupProtectedEffectCheckpoint,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridor,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RouteSegment


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _identity() -> RedLivingDexSetupExecutionIdentity:
    return RedLivingDexSetupExecutionIdentity(
        source_commit="a" * 40,
        source_bundle_sha256=_sha("source-bundle"),
        adapter_version_sha256=_sha("adapter-version"),
        state_schema_sha256=_sha("state-schema"),
        observation_schema_sha256=_sha("observation-schema"),
        route_registry_sha256=_sha("route-registry"),
        provider_registry_sha256=_sha("provider-registry"),
        runtime_contract_sha256=_sha("runtime-contract"),
    )


@pytest.fixture(autouse=True)
def _bind_fake_route_world_to_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the synthetic router Red-bound without shipping cartridge bytes."""

    monkeypatch.setattr(
        provider_plan,
        "_route_world_rom_sha256",
        lambda _world: _identity().rom_sha256,
    )


def _root(index: int) -> RedLivingDexActionFreeRootObservation:
    state = f"authentic-root-{index:02d}".encode("ascii")
    envelope = CapturedProgressEnvelope(
        state_sha256=hashlib.sha256(state).hexdigest(),
        checkpoint_id=f"provider-root-{index:02d}",
        checkpoint_label="action-free provider-plan root",
        checkpoints_completed=1,
        checkpoints_total=1,
        verified_objective_ids=("root_observed",),
    )
    envelope_bytes = (
        json.dumps(envelope.to_dict(), ensure_ascii=True, sort_keys=True).encode("ascii") + b"\n"
    )
    authenticated = RedLivingDexAuthenticatedSetupRoot(
        root_consumption_sha256=_sha(("claim", index)),
        state_bytes=state,
        envelope_bytes=envelope_bytes,
    )
    return RedLivingDexActionFreeRootObservation(
        root=authenticated,
        traversal=TraversalSnapshot(
            map_id=200 + index,
            at=(3, 4),
            ready=True,
            mode="land",
            capabilities=frozenset({"cut", "surf", "strength"}),
            last_outside_map=200 + index,
        ),
        facts=_facts(index),
        observed_state_sha256=authenticated.state_sha256,
        root_claim_available=True,
    )


def _facts(index: int) -> RedLivingDexProviderRootFacts:
    party_numbers = (9, 83, 143, 135, 106, 25)
    party = PartyObservation(
        tuple(
            PartyMemberObservation(
                slot=slot,
                species_id=red_internal_species_id(number),
                level=40,
                hp=100,
                max_hp=100,
                moves=(MoveObservation(1, 20),),
            )
            for slot, number in enumerate(party_numbers, start=1)
        )
    )
    party_specimens = tuple(
        LivingSpecimen(
            red_species_ref(number),
            40,
            CollectionLocation.PARTY,
            slot_index=slot,
        )
        for slot, number in enumerate(party_numbers, start=1)
    )
    boxed_numbers = (11, 11, 14, 14, 16, 19, 41)
    boxed_specimens = tuple(
        LivingSpecimen(
            red_species_ref(number),
            9,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=slot,
        )
        for slot, number in enumerate(boxed_numbers)
    )
    specimens = (*party_specimens, *boxed_specimens)
    collection = CollectionObservation(
        owned_species=frozenset(item.species_ref for item in specimens),
        specimens=specimens,
        party_size=6,
        party_limit=6,
        box_counts=(7, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        current_box_index=0,
        box_capacity=20,
    )
    return RedLivingDexProviderRootFacts(
        map_id=200 + index,
        at=(3, 4),
        input_ready=True,
        battle_state=0,
        party=party,
        collection=collection,
        available_story_objective_ids=frozenset(
            {
                "defeat_giovanni",
                "obtain_strength",
                "defeat_blaine",
                "cross_victory_road",
                "defeat_erika",
            }
        ),
        capture_item_count=5,
        recovery_item_count=8,
        immediate_capture_slots=13,
        bag_item_ids=frozenset({int(ItemId.GREAT_BALL)}),
        player_money=50_000,
        resources_satisfaction=0.25,
        world_knowledge_satisfaction=0.5,
    )


def _roots() -> tuple[RedLivingDexActionFreeRootObservation, ...]:
    return tuple(_root(index) for index in range(15))


def _corridors() -> tuple[RedLivingDexWildCorridor, ...]:
    sources = (
        "wild:Route2:grass",
        "wild:Route8:grass",
        "wild:Route11:grass",
        "wild:Route16:grass",
        "wild:Route21:grass",
        "wild:Route22:grass",
        "wild:Route24:grass",
    )
    return tuple(
        RedLivingDexWildCorridor(
            source,
            int(map_id_for_wild_source(source)),
            (2, 1),
            (1, 1),
        )
        for source in sources
    )


class _RouteWorld:
    def __init__(self, *, macro_graph: MacroGraph | None = None) -> None:
        self.macro_graph = MacroGraph({}) if macro_graph is None else macro_graph
        self.rom = b"immutable-red-route-world"

    def plan_feasible_to_map(
        self,
        start: TraversalSnapshot,
        goal_map: int,
        *,
        goal_at: tuple[int, int] | None = None,
    ) -> RoutePlan:
        terminal_at = goal_at if goal_at is not None else (goal_map % 10 + 1, 2)
        if start.map_id == goal_map:
            path = LocalPath(
                coordinates=(start.at, terminal_at),
                edges=(
                    LocalEdge(
                        target=terminal_at,
                        action="right",
                        required_mode="land",
                    ),
                ),
                modes=(start.mode, "land"),
            )
            return RoutePlan(
                macro_path=MacroPath((start.map_id,), ()),
                start_at=start.at,
                start_mode=start.mode,
                segments=(),
                terminal_approach=path,
                terminal_at=terminal_at,
                terminal_mode="land",
            )
        transition = MacroTransition(start.at, terminal_at, "right")
        edge = MacroEdge(
            target_map=goal_map,
            coordinate_transitions=(transition,),
        )
        segment = RouteSegment(
            source_map=start.map_id,
            target_map=goal_map,
            approach=LocalPath((start.at,), (), (start.mode,)),
            transition=transition,
            passage_kind="connection",
            transition_action_in_approach=False,
        )
        return RoutePlan(
            macro_path=MacroPath((start.map_id, goal_map), (edge,)),
            start_at=start.at,
            start_mode=start.mode,
            segments=(segment,),
            terminal_approach=None,
            terminal_at=terminal_at,
            terminal_mode="land",
        )


def _freeze(
    roots: tuple[RedLivingDexActionFreeRootObservation, ...] | None = None,
    *,
    before: RedLivingDexSetupProtectedEffectCheckpoint | None = None,
    after: RedLivingDexSetupProtectedEffectCheckpoint | None = None,
):
    checkpoint = RedLivingDexSetupProtectedEffectCheckpoint()
    return freeze_red_living_dex_provider_plan(
        _roots() if roots is None else roots,
        world=_RouteWorld(),
        corridors=_corridors(),
        execution_identity=_identity(),
        effects_before=checkpoint if before is None else before,
        effects_after=checkpoint if after is None else after,
    )


def test_freezes_complete_authentic_provider_capacity_without_effects() -> None:
    frozen = _freeze()

    assert tuple(recipe.origin_boundary.map_id for recipe in frozen.plan.recipes) == (
        int(MapId.ROUTE_24),
        int(MapId.ROUTE_24),
        int(MapId.CINNABAR_POKECENTER),
        int(MapId.CINNABAR_POKECENTER),
        int(MapId.ROUTE_2),
        int(MapId.ROUTE_2),
        int(MapId.VIRIDIAN_POKECENTER),
        int(MapId.VIRIDIAN_POKECENTER),
        int(MapId.CINNABAR_MART),
        int(MapId.CINNABAR_MART),
        int(MapId.VIRIDIAN_CITY),
        int(MapId.PEWTER_CITY),
        int(MapId.CELADON_POKECENTER),
        int(MapId.CINNABAR_ISLAND),
        int(MapId.ROUTE_21),
    )
    assert frozen.public_dict() == {
        "action_free_root_observations": 15,
        "cartridge_derived_corridors": 7,
        "claim_before_controller_input": True,
        "controller_actions": 0,
        "development_slots": 5,
        "emulator_frames": 0,
        "execution_identity_bound": True,
        "learner_effects": 0,
        "model_fits": 0,
        "option_count": 45,
        "outcomes": 0,
        "physical_origin_count": 10,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "provider_executions": 0,
        "retry_after_controller_input": False,
        "root_claims": 0,
        "routed_option_count": 37,
        "same_origin_fork_required": True,
        "schema": "pokemon.red.private-living-dex-provider-plan-freeze.v1",
        "semantic_family_count": 33,
        "semantic_family_minimum": 33,
        "slot_count": 15,
        "teacher_queries": 0,
        "train_slots": 10,
    }
    assert len({recipe.root_state_sha256 for recipe in frozen.plan.recipes}) == 15
    assert (
        len(
            {
                provider.expected_family_sha256
                for recipe in frozen.plan.recipes
                for provider in recipe.providers
            }
        )
        == 33
    )
    assert frozen.effects_before == frozen.effects_after


def test_rejects_cross_joined_consumed_or_repeated_roots_before_planning() -> None:
    root = _root(0)
    with pytest.raises(RedLivingDexProviderPlanError, match="another state"):
        replace(root, observed_state_sha256="f" * 64)
    with pytest.raises(RedLivingDexProviderPlanError, match="already consumed"):
        replace(root, root_claim_available=False)
    with pytest.raises(RedLivingDexProviderPlanError, match="observations disagree"):
        replace(root, facts=replace(root.facts, map_id=1))

    roots = list(_roots())
    roots[-1] = roots[0]
    with pytest.raises(RedLivingDexProviderPlanError, match="repeats root claims"):
        _freeze(tuple(roots))


def test_rejects_a_root_that_cannot_supply_its_scheduled_story_family() -> None:
    roots = list(_roots())
    erika = roots[12]
    roots[12] = replace(
        erika,
        facts=replace(
            erika.facts,
            available_story_objective_ids=frozenset(
                erika.facts.available_story_objective_ids.difference({"defeat_erika"})
            ),
        ),
    )

    with pytest.raises(RedLivingDexProviderPlanError, match="dependency-legal"):
        _freeze(tuple(roots))


def test_rejects_roots_without_encounter_resupply_or_storage_preconditions() -> None:
    cases = (
        (0, {"capture_item_count": 0}, "acquisition root"),
        (0, {"world_knowledge_satisfaction": 1.0}, "exploration root"),
        (4, {"player_money": 0}, "resupply root"),
    )
    for slot_index, changes, reason in cases:
        roots = list(_roots())
        root = roots[slot_index]
        roots[slot_index] = replace(root, facts=replace(root.facts, **changes))
        with pytest.raises(RedLivingDexProviderPlanError, match=reason):
            _freeze(tuple(roots))

    roots = list(_roots())
    root = roots[1]
    counts = list(root.facts.collection.box_counts)
    counts[1] = counts[0]
    roots[1] = replace(
        root,
        facts=replace(
            root.facts,
            collection=replace(root.facts.collection, box_counts=tuple(counts)),
        ),
    )
    with pytest.raises(RedLivingDexProviderPlanError, match="storage root"):
        _freeze(tuple(roots))


def test_rejects_roots_without_targeted_evolution_or_development_specimens() -> None:
    roots = list(_roots())
    evolution = roots[1]
    source_ref = red_species_ref(11)
    roots[1] = replace(
        evolution,
        facts=replace(
            evolution.facts,
            collection=replace(
                evolution.facts.collection,
                specimens=tuple(
                    specimen
                    for specimen in evolution.facts.collection.specimens
                    if specimen.species_ref != source_ref
                ),
            ),
        ),
    )
    with pytest.raises(RedLivingDexProviderPlanError, match="boxed precursor"):
        _freeze(tuple(roots))

    roots = list(_roots())
    development = roots[0]
    target_internal = red_internal_species_id(83)
    members = list(development.facts.party.members)
    members[-1] = replace(members[-1], species_id=target_internal)
    specimens = list(development.facts.collection.specimens)
    specimens[5] = replace(specimens[5], species_ref=red_species_ref(83))
    roots[0] = replace(
        development,
        facts=replace(
            development.facts,
            party=PartyObservation(tuple(members)),
            collection=replace(
                development.facts.collection,
                specimens=tuple(specimens),
            ),
        ),
    )
    with pytest.raises(RedLivingDexProviderPlanError, match="unique trainee"):
        _freeze(tuple(roots))


def test_rejects_protected_effect_or_corridor_substitution() -> None:
    before = RedLivingDexSetupProtectedEffectCheckpoint()
    after = RedLivingDexSetupProtectedEffectCheckpoint(emulator_frames=1)
    with pytest.raises(RedLivingDexProviderPlanError, match="protected effect"):
        _freeze(before=before, after=after)

    with pytest.raises(RedLivingDexProviderPlanError, match="corridor inventory"):
        freeze_red_living_dex_provider_plan(
            _roots(),
            world=_RouteWorld(),
            corridors=_corridors()[:-1],
            execution_identity=_identity(),
            effects_before=before,
            effects_after=before,
        )


def test_rejects_route_world_from_another_cartridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_plan,
        "_route_world_rom_sha256",
        lambda _world: "0" * 64,
    )

    with pytest.raises(RedLivingDexProviderPlanError, match="another cartridge"):
        _freeze()


def test_terminal_projection_updates_retained_outside_instead_of_copying_stale_state() -> None:
    start = TraversalSnapshot(
        map_id=1,
        at=(4, 4),
        ready=True,
        mode="land",
        last_outside_map=99,
    )
    transition = MacroTransition((4, 4), (2, 2), "up")
    edge = MacroEdge(
        target_map=100,
        kind="warp",
        at=(4, 4),
        arrival_at=(2, 2),
        coordinate_transitions=(transition,),
    )
    plan = RoutePlan(
        macro_path=MacroPath((1, 100), (edge,)),
        start_at=(4, 4),
        start_mode="land",
        segments=(
            RouteSegment(
                source_map=1,
                target_map=100,
                approach=LocalPath(((4, 4),), (), ("land",)),
                transition=transition,
                passage_kind="warp",
                transition_action_in_approach=False,
            ),
        ),
        terminal_approach=None,
        terminal_at=(2, 2),
        terminal_mode="land",
    )
    world = _RouteWorld(macro_graph=MacroGraph({}, outside_nodes=frozenset({1})))

    terminal = red_living_dex_route_terminal_snapshot(world, start, plan)

    assert terminal.map_id == 100
    assert terminal.last_outside_map == 1
    assert terminal.last_outside_map != start.last_outside_map


def test_freezer_source_has_no_state_or_execution_authority() -> None:
    source = __import__(
        "pokemon_red_completion.red_living_dex_provider_plan",
        fromlist=["unused"],
    ).__file__
    assert source is not None
    payload = Path(source).read_text(encoding="utf-8")

    for forbidden in (
        "load_state_bytes(",
        ".execute(",
        ".press(",
        ".tick(",
        "teacher_choice",
        "model.fit(",
    ):
        assert forbidden not in payload
