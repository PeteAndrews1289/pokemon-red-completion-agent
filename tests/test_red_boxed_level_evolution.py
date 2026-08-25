from __future__ import annotations

import json
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_boxed_level_evolution as boxed
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import RawGameState, RedCurrentBoxState
from pokemon_red_completion.red_boxed_level_evolution import (
    BoundedEvolutionTrainingResult,
    BoxedLevelEvolutionExecutionReport,
    BoxedLevelEvolutionPlan,
    ObservedSemanticBoundaryBinding,
    ObservedSemanticBoundaryReport,
    RedBoxedLevelEvolutionAdapter,
    RedBoxedLevelEvolutionError,
)
from pokemon_red_completion.red_collection import (
    red_internal_species_id,
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    SemanticVenueRouteBinding,
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    RedDependencySpeciesBinding,
    red_dual_capability_scenario_specs,
)
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUX_SPECIES_ID,
    HITMONLEE_SPECIES_ID,
    JOLTEON_SPECIES_ID,
    SNORLAX_SPECIES_ID,
)
from pokemon_red_completion.red_pc_storage import (
    RedPCDepositReport,
    RedPCWithdrawReport,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import plan_route

MAP_ID = 1
PRECURSOR = red_internal_species_id(11)
EVOLVED = red_internal_species_id(12)
DIGLETT_SPECIES_ID = red_internal_species_id(50)
RESET = "a" * 64


def _routes() -> tuple[SemanticVenueRouteBinding, SemanticVenueRouteBinding]:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (LocalEdge((0, 0), action="left"),),
        }
    )
    macro = MacroGraph({MAP_ID: ()})
    to_pc = plan_route(
        macro,
        {MAP_ID: graph},
        MAP_ID,
        (0, 0),
        MAP_ID,
        goal_at=(0, 1),
    )
    to_training = plan_route(
        macro,
        {MAP_ID: graph},
        MAP_ID,
        (0, 1),
        MAP_ID,
        goal_at=(0, 0),
    )
    return (
        SemanticVenueRouteBinding(to_pc, "b" * 64),
        SemanticVenueRouteBinding(to_training, "c" * 64),
    )


@dataclass
class _World:
    party: list[int]
    box: list[int]
    at: tuple[int, int] = (0, 0)
    actions_executed: int = 0

    def __post_init__(self) -> None:
        self.log: list[str] = []

    def execute(self, action: MacroAction) -> MacroAction:
        self.actions_executed += 1
        if action.kind is MacroActionKind.MOVE:
            assert isinstance(action.value, str)
            y, x = self.at
            if action.value == "right":
                self.at = (y, x + 1)
            elif action.value == "left":
                self.at = (y, x - 1)
            else:  # pragma: no cover - fixture routes contain only left/right
                raise AssertionError(action.value)
            self.log.append(f"route:{action.value}")
        return action

    def observe(self) -> TraversalSnapshot:
        return TraversalSnapshot(MAP_ID, self.at, True)

    def read(self) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=MAP_ID,
            player_x=self.at[1],
            player_y=self.at[0],
            party_count=len(self.party),
            party_species_ids=tuple(self.party),
            battle_state=0,
        )

    def read_input_readiness(self) -> object:
        return SimpleNamespace(ready=True)

    def read_current_box_state(self) -> RedCurrentBoxState:
        return RedCurrentBoxState(0, tuple(self.box), tuple(10 for _ in self.box))

    def collection(self) -> CollectionObservation:
        specimens = tuple(
            LivingSpecimen(
                red_species_ref(red_internal_species_number(species)),
                30,
                CollectionLocation.PARTY,
                slot_index=index,
            )
            for index, species in enumerate(self.party)
        ) + tuple(
            LivingSpecimen(
                red_species_ref(red_internal_species_number(species)),
                4 if species == PRECURSOR else 20,
                CollectionLocation.BOX,
                container_index=0,
                slot_index=index,
            )
            for index, species in enumerate(self.box)
        )
        return CollectionObservation(
            owned_species=frozenset(item.species_ref for item in specimens),
            specimens=specimens,
            party_size=len(self.party),
            party_limit=6,
            box_counts=(len(self.box),),
            current_box_index=0,
            box_capacity=20,
        )


def _world() -> _World:
    return _World(
        [
            BLASTOISE_SPECIES_ID,
            DUX_SPECIES_ID,
            DIGLETT_SPECIES_ID,
            JOLTEON_SPECIES_ID,
            SNORLAX_SPECIES_ID,
            HITMONLEE_SPECIES_ID,
        ],
        [PRECURSOR, PRECURSOR, red_internal_species_id(25)],
    )


def _plan() -> BoxedLevelEvolutionPlan:
    to_pc, to_training = _routes()
    return BoxedLevelEvolutionPlan(
        RESET,
        RedDependencySpeciesBinding(red_species_ref(11), red_species_ref(12)),
        PRECURSOR,
        EVOLVED,
        0,
        1,
        6,
        HITMONLEE_SPECIES_ID,
        to_pc,
        to_training,
        "d" * 64,
    )


def _observed_pc_plan() -> BoxedLevelEvolutionPlan:
    _to_pc, to_training = _routes()
    return BoxedLevelEvolutionPlan(
        RESET,
        RedDependencySpeciesBinding(red_species_ref(11), red_species_ref(12)),
        PRECURSOR,
        EVOLVED,
        0,
        1,
        6,
        HITMONLEE_SPECIES_ID,
        ObservedSemanticBoundaryBinding(MAP_ID, (0, 1), "e" * 64),
        to_training,
        "d" * 64,
    )


def _patch_storage(monkeypatch: pytest.MonkeyPatch, world: _World) -> None:
    def open_pc(_actions: object, _reader: object, **_kwargs: object) -> None:
        world.log.append("pc:open")

    def deposit(
        _actions: object,
        _reader: object,
        *,
        party_slot: int,
        expected_species_id: int,
        **_kwargs: object,
    ) -> RedPCDepositReport:
        party_before = tuple(world.party)
        box_before = tuple(world.box)
        assert world.party[party_slot - 1] == expected_species_id
        world.party.pop(party_slot - 1)
        world.box.append(expected_species_id)
        world.log.append("pc:deposit")
        return RedPCDepositReport(
            expected_species_id,
            party_slot,
            party_before,
            tuple(world.party),
            0,
            box_before,
            tuple(world.box),
        )

    def withdraw(
        _actions: object,
        _reader: object,
        *,
        box_slot: int,
        expected_species_id: int,
        **_kwargs: object,
    ) -> RedPCWithdrawReport:
        party_before = tuple(world.party)
        box_before = tuple(world.box)
        assert world.box[box_slot - 1] == expected_species_id
        world.box.pop(box_slot - 1)
        world.party.append(expected_species_id)
        world.log.append("pc:withdraw")
        return RedPCWithdrawReport(
            expected_species_id,
            box_slot,
            party_before,
            tuple(world.party),
            0,
            box_before,
            tuple(world.box),
        )

    def close(_actions: object, _reader: object) -> None:
        world.log.append("pc:close")

    monkeypatch.setattr(boxed, "open_bills_pc", open_pc)
    monkeypatch.setattr(boxed, "deposit_party_member", deposit)
    monkeypatch.setattr(boxed, "withdraw_box_member", withdraw)
    monkeypatch.setattr(boxed, "close_menu", close)


def _adapter(
    monkeypatch: pytest.MonkeyPatch,
    world: _World,
    *,
    settle: bool = True,
    plan: BoxedLevelEvolutionPlan | None = None,
) -> RedBoxedLevelEvolutionAdapter:
    _patch_storage(monkeypatch, world)

    def train(precursor: int, evolved: int) -> BoundedEvolutionTrainingResult:
        world.log.append("training")
        assert world.at == (0, 0)
        assert precursor == PRECURSOR and evolved == EVOLVED
        if settle:
            world.party[world.party.index(precursor)] = evolved
        return BoundedEvolutionTrainingResult(3, 0)

    return RedBoxedLevelEvolutionAdapter(
        plan or _plan(),
        world,
        world,
        world,
        world.collection,
        train,
    )


def test_qualification_is_action_free_and_generic_for_a_boxed_underlevel_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    adapter = _adapter(monkeypatch, world)
    before = dependency_specimen_ledger(world.collection())
    scenario = red_dual_capability_scenario_specs()[1]

    capability = adapter.qualify(scenario, before)

    assert world.actions_executed == 0
    assert world.log == []
    assert capability.evidence.kind.value == "evolve_species"
    assert capability.evidence.role.value == "bounded_training_evolution"
    public = json.dumps(adapter.plan.public_dict(), sort_keys=True).lower()
    assert red_species_ref(11) not in public
    assert red_species_ref(12) not in public
    assert str(PRECURSOR) not in public
    assert adapter.plan.skill_binding_sha256 not in public


def test_route_backed_skill_identity_remains_compatible_with_published_v1() -> None:
    assert (
        _plan().skill_binding_sha256
        == "fcf6f7882ceafc34eb8b5883e64afcb4de17750cd4f52c3113c9203476689ef8"
    )
    assert _observed_pc_plan().skill_binding_sha256 != _plan().skill_binding_sha256


def test_selected_boxed_evolution_routes_stores_trains_and_proves_exact_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    adapter = _adapter(monkeypatch, world)
    before = dependency_specimen_ledger(world.collection())
    scenario = red_dual_capability_scenario_specs()[1]

    report = adapter.qualify(scenario, before).execute()

    assert isinstance(report, BoxedLevelEvolutionExecutionReport)
    assert report.after_ledger.count(red_species_ref(11)) == 1
    assert report.after_ledger.count(red_species_ref(12)) == 1
    assert report.public_dict()["exact_evolution_transition"] is True
    assert report.public_dict()["required_living_preserved"] is True
    assert world.log == [
        "route:right",
        "pc:open",
        "pc:deposit",
        "pc:withdraw",
        "pc:close",
        "route:left",
        "training",
    ]
    assert HITMONLEE_SPECIES_ID in world.box
    assert HITMONLEE_SPECIES_ID not in world.party
    assert EVOLVED in world.party
    encoded = json.dumps(report.public_dict(), sort_keys=True).lower()
    assert red_species_ref(11) not in encoded
    assert red_species_ref(12) not in encoded


def test_exact_pc_start_uses_an_observed_boundary_without_a_fake_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    world.at = (0, 1)
    adapter = _adapter(monkeypatch, world, plan=_observed_pc_plan())
    before = dependency_specimen_ledger(world.collection())
    scenario = red_dual_capability_scenario_specs()[1]

    capability = adapter.qualify(scenario, before)

    assert world.actions_executed == 0
    assert world.log == []
    report = capability.execute()
    assert isinstance(report, BoxedLevelEvolutionExecutionReport)
    assert isinstance(report.route_to_pc, ObservedSemanticBoundaryReport)
    assert report.route_to_pc.controller_actions == 0
    assert report.public_dict()["semantic_routes_passed"] == 1
    assert report.public_dict()["observed_semantic_boundaries_passed"] == 1
    assert report.public_dict()["acknowledged_route_steps"] == 1
    assert world.log == [
        "pc:open",
        "pc:deposit",
        "pc:withdraw",
        "pc:close",
        "route:left",
        "training",
    ]
    encoded = json.dumps(report.public_dict(), sort_keys=True).lower()
    assert "(0, 1)" not in encoded
    assert isinstance(adapter.plan.route_to_pc, ObservedSemanticBoundaryBinding)
    assert adapter.plan.route_to_pc.binding_sha256 not in encoded


def test_observed_pc_boundary_rejects_coordinate_drift_without_acting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    monkeypatch.setattr(
        world,
        "observe",
        lambda: TraversalSnapshot(MAP_ID, (0, 1), True),
    )
    adapter = _adapter(monkeypatch, world, plan=_observed_pc_plan())
    before = dependency_specimen_ledger(world.collection())

    with pytest.raises(RedBoxedLevelEvolutionError, match="live game state differs"):
        adapter.qualify(red_dual_capability_scenario_specs()[1], before)
    assert world.actions_executed == 0
    assert world.log == []


def test_observed_pc_boundary_rejects_battle_state_without_acting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    world.at = (0, 1)
    original_read = world.read
    monkeypatch.setattr(world, "read", lambda: replace(original_read(), battle_state=1))
    adapter = _adapter(monkeypatch, world, plan=_observed_pc_plan())
    before = dependency_specimen_ledger(world.collection())

    with pytest.raises(RedBoxedLevelEvolutionError, match="live game state differs"):
        adapter.qualify(red_dual_capability_scenario_specs()[1], before)
    assert world.actions_executed == 0
    assert world.log == []


def test_observed_pc_boundary_rejects_an_observer_that_changes_action_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    world.at = (0, 1)

    def acting_observer() -> TraversalSnapshot:
        world.actions_executed += 1
        return TraversalSnapshot(MAP_ID, (0, 1), True)

    monkeypatch.setattr(world, "observe", acting_observer)
    adapter = _adapter(monkeypatch, world, plan=_observed_pc_plan())
    before = dependency_specimen_ledger(world.collection())

    with pytest.raises(RedBoxedLevelEvolutionError, match="live game state differs"):
        adapter.qualify(red_dual_capability_scenario_specs()[1], before)
    assert world.actions_executed == 1
    assert world.log == []


def test_qualification_fails_closed_when_the_frozen_box_slot_drifts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    world.box[0], world.box[2] = world.box[2], world.box[0]
    adapter = _adapter(monkeypatch, world)
    before = dependency_specimen_ledger(world.collection())

    with pytest.raises(RedBoxedLevelEvolutionError, match="current-box boundary"):
        adapter.qualify(red_dual_capability_scenario_specs()[1], before)
    assert world.actions_executed == 0
    assert world.log == []


def test_independent_collection_observer_rejects_a_trainer_that_did_not_evolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world()
    adapter = _adapter(monkeypatch, world, settle=False)
    before = dependency_specimen_ledger(world.collection())

    with pytest.raises(
        RedBoxedLevelEvolutionError,
        match="independent collection observation differs",
    ):
        adapter.qualify(red_dual_capability_scenario_specs()[1], before).execute()


def test_plan_rejects_an_internal_species_identity_that_does_not_match_family() -> None:
    plan = _plan()

    with pytest.raises(RedBoxedLevelEvolutionError, match="internal species binding"):
        BoxedLevelEvolutionPlan(
            plan.reset_state_sha256,
            plan.species_binding,
            red_internal_species_id(14),
            plan.evolved_internal_species_id,
            plan.current_box_index,
            plan.precursor_box_slot,
            plan.deposit_party_slot,
            plan.deposit_internal_species_id,
            plan.route_to_pc,
            plan.route_to_training,
            plan.training_binding_sha256,
        )
