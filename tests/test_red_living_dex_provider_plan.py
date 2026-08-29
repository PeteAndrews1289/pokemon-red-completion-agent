from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion import red_living_dex_causal_inventory as causal_inventory
from pokemon_red_completion import red_living_dex_provider_plan as provider_plan
from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.claim_first_admission import ClaimFirstRootPair
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
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.living_dex_causal_capacity_schedule import (
    build_living_dex_causal_capacity_schedule,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionContext
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
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_causal_capacity import (
    RedLivingDexCausalCapacityAssignment,
    RedLivingDexCausalCapacityError,
    audit_red_living_dex_causal_capacity,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalInventoryError,
    RedLivingDexCausalRootCapability,
    audit_red_living_dex_causal_inventory,
    census_red_living_dex_causal_inventory,
    schedule_red_living_dex_clustered_integration,
)
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    map_id_for_wild_source,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
    RedLivingDexClaimedRootObservation,
    RedLivingDexProviderPlanError,
    RedLivingDexProviderRootFacts,
    build_red_living_dex_provider_recipe_for_action_free_root,
    build_red_living_dex_provider_recipe_for_claimed_root,
    freeze_red_living_dex_provider_plan,
    red_living_dex_route_terminal_snapshot,
    select_red_living_dex_provider_roots,
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
        option_context=LivingDexOptionContext(
            (index % 3) / 2,
            ((index + 1) % 3) / 2,
            ((index + 2) % 3) / 2,
            ((index + 3) % 3) / 2,
            ((index + 4) % 3) / 2,
            ((index + 5) % 3) / 2,
            ((index + 6) % 3) / 2,
        ),
        independence_lineage_sha256=_sha(("lineage", index)),
        prospective_independence_authenticated=True,
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


def _claimed(index: int) -> RedLivingDexClaimedRootObservation:
    action_free = _root(index)
    root = action_free.root
    pair = ClaimFirstRootPair(
        logical_root_sha256=root.root_consumption_sha256,
        physical_root_sha256=root.physical_root_sha256,
        stage="setup-capture",
        execution_identity_sha256=_sha(("execution", index)),
        plan_sha256=_sha(("plan", index)),
        slot_sha256=_sha(("slot", index)),
        runner_sha256=_sha(("runner", index)),
        source_commit="b" * 40,
    )
    return RedLivingDexClaimedRootObservation(
        root=root,
        traversal=action_free.traversal,
        facts=action_free.facts,
        observed_state_sha256=action_free.observed_state_sha256,
        pair_claim=pair,
    )


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


def test_current_provider_plan_is_truthfully_only_an_integration_floor() -> None:
    frozen = _freeze()
    slots = build_red_living_dex_prospective_capture_plan().slots
    roots = _roots()
    assignments = tuple(
        RedLivingDexCausalCapacityAssignment(
            slot=slot,
            recipe=recipe,
            root=root,
            focus_kind=slot.available_option_kinds[0],
            assigned_candidate_index=(
                0 if slot.partition is LivingDexCapturePartition.TRAIN else None
            ),
        )
        for slot, recipe, root in zip(
            slots,
            frozen.plan.recipes,
            roots,
            strict=True,
        )
    )

    audit = audit_red_living_dex_causal_capacity(assignments)

    assert not audit.ready
    assert audit.train_contexts == 10
    assert audit.development_contexts == 5
    assert audit.distinct_physical_roots == 15
    assert audit.distinct_independence_lineages == 15
    assert "insufficient_train_contexts" in audit.reasons
    assert "insufficient_development_contexts" in audit.reasons
    assert audit.public_dict()["private_identity_fields"] == 0


def test_action_free_inventory_computes_exact_powered_root_deficits() -> None:
    checkpoint = RedLivingDexSetupProtectedEffectCheckpoint()

    audit = census_red_living_dex_causal_inventory(
        _roots(),
        world=_RouteWorld(),
        corridors=_corridors(),
        effects_before=checkpoint,
        effects_after=checkpoint,
    )

    assert not audit.inventory_sufficient
    assert audit.roots_observed == 15
    assert audit.distinct_physical_roots == 15
    assert audit.distinct_independence_lineages == 15
    assert audit.independence_qualified_roots == 15
    assert audit.unqualified_lineage_roots == 0
    assert audit.train_maximum_matching == 15
    assert audit.development_maximum_matching == 15
    assert audit.combined_maximum_matching == 15
    assert audit.train_context_deficit == 75
    assert audit.development_context_deficit == 90
    assert audit.combined_context_deficit == 180
    assert all(count == 15 for count in audit.train_template_compatible_root_counts)
    assert all(
        count == 15 for count in audit.development_template_compatible_root_counts
    )
    public = audit.public_dict()
    assert public["minimum_new_independent_roots_lower_bound"] == 180
    assert public["collection_authorized"] is False
    assert public["controller_actions"] == 0
    assert public["emulator_frames"] == 0
    assert public["root_claims"] == 0
    assert public["provider_executions"] == 0


def test_action_free_inventory_rejects_duplicate_lineage_or_protected_effect() -> None:
    checkpoint = RedLivingDexSetupProtectedEffectCheckpoint()
    roots = list(_roots())
    roots[1] = replace(
        roots[1],
        independence_lineage_sha256=roots[0].independence_lineage_sha256,
    )
    with pytest.raises(RedLivingDexCausalInventoryError, match="independence lineage"):
        census_red_living_dex_causal_inventory(
            tuple(roots),
            world=_RouteWorld(),
            corridors=_corridors(),
            effects_before=checkpoint,
            effects_after=checkpoint,
        )

    with pytest.raises(RedLivingDexCausalInventoryError, match="protected effect"):
        census_red_living_dex_causal_inventory(
            _roots(),
            world=_RouteWorld(),
            corridors=_corridors(),
            effects_before=checkpoint,
            effects_after=replace(checkpoint, emulator_frames=1),
        )


def test_red_clustered_integration_reuses_roots_without_crossing_partitions() -> None:
    plan = build_red_living_dex_prospective_capture_plan()
    roots = tuple(
        replace(
            root,
            cluster_partition=(
                "train" if index < 4 else "development" if index < 6 else None
            ),
        )
        for index, root in enumerate(_roots())
    )
    capabilities: list[RedLivingDexCausalRootCapability] = []
    for root in roots[:6]:
        for template_ordinal, slot in enumerate(plan.slots):
            expected_partition = (
                "train"
                if slot.partition is LivingDexCapturePartition.TRAIN
                else "development"
            )
            if root.cluster_partition != expected_partition:
                continue
            recipe = build_red_living_dex_provider_recipe_for_action_free_root(
                slot,
                root,
                world=_RouteWorld(),
                corridors=_corridors(),
            )
            capabilities.append(
                RedLivingDexCausalRootCapability(
                    root=root,
                    template_ordinal=template_ordinal,
                    slot=slot,
                    recipe=recipe,
                )
            )

    schedule = schedule_red_living_dex_clustered_integration(
        tuple(capabilities)
    )
    public = schedule.public_dict()

    assert public["train_scenarios"] == 8
    assert public["development_scenarios"] == 4
    assert public["train_lineages"] == 4
    assert public["development_lineages"] == 2
    assert public["lineage_overlap"] == 0
    assert public["maximum_observed_scenarios_per_lineage"] == 2
    assert all(
        assignment.capability.partition
        == (
            "train"
            if assignment.capability.lineage_sha256
            in {root.independence_lineage_sha256 for root in roots[:4]}
            else "development"
        )
        for assignment in schedule.assignments
    )

def test_action_free_inventory_rejects_interleaved_template_partitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = build_red_living_dex_prospective_capture_plan()
    train = tuple(
        slot for slot in plan.slots if slot.partition is LivingDexCapturePartition.TRAIN
    )
    development = tuple(
        slot
        for slot in plan.slots
        if slot.partition is LivingDexCapturePartition.DEVELOPMENT
    )
    interleaved = replace(
        plan,
        slots=(train[0], development[0], *train[1:], *development[1:]),
    )
    monkeypatch.setattr(
        causal_inventory,
        "build_red_living_dex_prospective_capture_plan",
        lambda: interleaved,
    )

    with pytest.raises(RedLivingDexCausalInventoryError, match="not contiguous"):
        audit_red_living_dex_causal_inventory(_roots(), ())


def test_action_free_inventory_matching_reassigns_an_earlier_greedy_root() -> None:
    plan = build_red_living_dex_prospective_capture_plan()
    train_slots = tuple(
        slot
        for slot in plan.slots
        if slot.partition is LivingDexCapturePartition.TRAIN
    )
    schedule = build_living_dex_causal_capacity_schedule(
        tuple(slot.available_option_kinds for slot in train_slots),
        tuple(
            slot.available_option_kinds
            for slot in plan.slots
            if slot.partition is LivingDexCapturePartition.DEVELOPMENT
        ),
    )
    one_per_template = tuple(
        next(
            item
            for item in schedule.slots
            if item.partition == "train" and item.template_ordinal == template
        )
        for template in range(3)
    )
    roots = ("a" * 64, "b" * 64, "c" * 64)
    compatible = {index: set() for index in range(15)}
    compatible[0] = {roots[0], roots[1]}
    compatible[1] = {roots[0], roots[2]}
    compatible[2] = {roots[0], roots[2]}

    assert (
        causal_inventory._maximum_matching(
            one_per_template,
            compatible,
            roots,
            development_template_offset=0,
        )
        == 3
    )


def test_legacy_physical_digest_does_not_mint_an_independent_capacity_root() -> None:
    roots = list(_roots())
    roots[0] = replace(roots[0], prospective_independence_authenticated=False)
    frozen = _freeze()
    slots = build_red_living_dex_prospective_capture_plan().slots
    capabilities = tuple(
        RedLivingDexCausalRootCapability(
            root=roots[index],
            template_ordinal=index,
            slot=slots[index],
            recipe=frozen.plan.recipes[index],
        )
        for index in range(1, len(roots))
    )

    audit = audit_red_living_dex_causal_inventory(
        tuple(roots),
        capabilities,
    )

    assert audit.roots_observed == 15
    assert audit.independence_qualified_roots == 14
    assert audit.unqualified_lineage_roots == 1
    assert audit.distinct_independence_lineages == 14
    assert audit.combined_maximum_matching <= 14


def test_red_capacity_rejects_missing_pressure_or_lineage_truth() -> None:
    frozen = _freeze()
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    root = _root(0)
    with pytest.raises(RedLivingDexCausalCapacityError, match="pressure"):
        RedLivingDexCausalCapacityAssignment(
            slot,
            frozen.plan.recipes[0],
            replace(root, option_context=None),
            slot.available_option_kinds[0],
            0,
        )
    with pytest.raises(RedLivingDexCausalCapacityError, match="lineage"):
        RedLivingDexCausalCapacityAssignment(
            slot,
            frozen.plan.recipes[0],
            replace(
                root,
                independence_lineage_sha256=None,
                prospective_independence_authenticated=False,
            ),
            slot.available_option_kinds[0],
            0,
        )
    with pytest.raises(RedLivingDexCausalCapacityError, match="prospectively"):
        RedLivingDexCausalCapacityAssignment(
            slot,
            frozen.plan.recipes[0],
            replace(root, prospective_independence_authenticated=False),
            slot.available_option_kinds[0],
            0,
        )


def test_cold_resolver_rebuilds_only_the_claimed_exact_recipe() -> None:
    frozen = _freeze()
    observation = _claimed(0)

    resolved = build_red_living_dex_provider_recipe_for_claimed_root(
        0,
        observation,
        world=_RouteWorld(),
        corridors=_corridors(),
        expected_rom_sha256=_identity().rom_sha256,
    )

    assert resolved == frozen.plan.recipes[0]
    assert resolved.recipe_sha256 == frozen.plan.recipes[0].recipe_sha256
    assert observation.pair_claim_sha256 == observation.pair_claim.claim_sha256


def test_cold_resolver_rejects_unclaimed_cross_joined_or_wrong_cartridge_input() -> None:
    observation = _claimed(0)
    with pytest.raises(TypeError, match="claimed observation"):
        build_red_living_dex_provider_recipe_for_claimed_root(
            0,
            _root(0),  # type: ignore[arg-type]
            world=_RouteWorld(),
            corridors=_corridors(),
            expected_rom_sha256=_identity().rom_sha256,
        )
    with pytest.raises(RedLivingDexProviderPlanError, match="another root pair"):
        replace(
            observation,
            pair_claim=replace(
                observation.pair_claim,
                logical_root_sha256=_sha("other-logical-root"),
            ),
        )
    with pytest.raises(RedLivingDexProviderPlanError, match="another cartridge"):
        build_red_living_dex_provider_recipe_for_claimed_root(
            0,
            observation,
            world=_RouteWorld(),
            corridors=_corridors(),
            expected_rom_sha256="f" * 64,
        )


def test_selector_builds_one_prospectively_partitioned_unique_root_assignment() -> None:
    checkpoint = RedLivingDexSetupProtectedEffectCheckpoint()
    roots = _roots()

    selected = select_red_living_dex_provider_roots(
        roots,
        world=_RouteWorld(),
        corridors=_corridors(),
        effects_before=checkpoint,
        effects_after=checkpoint,
    )

    assert len(selected) == 15
    assert len({item.root.physical_root_sha256 for item in selected}) == 15
    assert set(selected) == set(roots)


def test_selector_routes_only_candidates_needed_for_the_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = RedLivingDexSetupProtectedEffectCheckpoint()
    roots = _roots()
    calls = 0
    original = provider_plan._build_slot_recipe

    def build(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(provider_plan, "_build_slot_recipe", build)

    selected = select_red_living_dex_provider_roots(
        roots,
        world=_RouteWorld(),
        corridors=_corridors(),
        effects_before=checkpoint,
        effects_after=checkpoint,
    )

    assert len(selected) == 15
    assert calls < len(roots) * len(roots)


def test_selector_rejects_inventory_shortfall_and_uncovered_slot() -> None:
    checkpoint = RedLivingDexSetupProtectedEffectCheckpoint()
    roots = _roots()
    with pytest.raises(RedLivingDexProviderPlanError, match="every prospective slot"):
        select_red_living_dex_provider_roots(
            roots[:14],
            world=_RouteWorld(),
            corridors=_corridors(),
            effects_before=checkpoint,
            effects_after=checkpoint,
        )

    candidates = list(roots)
    for index, root in enumerate(candidates):
        candidates[index] = replace(
            root,
            facts=replace(
                root.facts,
                available_story_objective_ids=frozenset(
                    root.facts.available_story_objective_ids.difference(
                        {"cross_victory_road"}
                    )
                ),
            ),
        )
    with pytest.raises(RedLivingDexProviderPlanError, match="uncovered slot"):
        select_red_living_dex_provider_roots(
            tuple(candidates),
            world=_RouteWorld(),
            corridors=_corridors(),
            effects_before=checkpoint,
            effects_after=checkpoint,
        )


def test_selector_backtracks_when_the_first_complete_join_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = RedLivingDexSetupProtectedEffectCheckpoint()
    roots = _roots()
    candidates = (roots[1], roots[0], *roots[2:])
    first_complete_last = sorted(
        item.root.physical_root_sha256 for item in candidates
    )[9]
    complete_joins = 0
    original = provider_plan.build_red_living_dex_provider_recipes

    def join(selected, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal complete_joins
        complete_joins += 1
        if selected[9].root.physical_root_sha256 == first_complete_last:
            raise RedLivingDexProviderPlanError("synthetic cross-slot collision")
        return original(selected, **kwargs)

    monkeypatch.setattr(provider_plan, "build_red_living_dex_provider_recipes", join)

    selected = select_red_living_dex_provider_roots(
        candidates,
        world=_RouteWorld(),
        corridors=_corridors(),
        effects_before=checkpoint,
        effects_after=checkpoint,
    )

    assert selected[9].root.physical_root_sha256 != first_complete_last
    assert complete_joins >= 2


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
