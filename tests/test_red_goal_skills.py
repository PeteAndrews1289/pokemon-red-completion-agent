from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalFailureReason,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.goal_manager_state import CompletionProgress
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    MapId,
    RamAddress,
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist
from pokemon_red_completion.red_acquisition import (
    RedAreaExecutionError,
    RedAreaExecutionPolicy,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_collection import (
    red_collection_observation,
    red_internal_species_number,
    red_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_manager import PokemonRedGoalStateAdapter
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedBoxSwitchGoalProvider,
    RedCenterRestoreGoalProvider,
    RedControlRecoveryGoalProvider,
    RedEncounterDiscoveryGoalProvider,
    RedEncounterSourceDevelopmentGoalProvider,
    RedFieldRestoreGoalProvider,
    RedGoalSkillAvailability,
    RedGoalSkillError,
    RedMartPurchase,
    RedMartResupplyGoalProvider,
    RedProgressGoalProvider,
    RedRouteGoalProvider,
)
from pokemon_red_completion.red_party import party_observation_from_raw
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan


def _graph() -> QuestGraph:
    return QuestGraph(
        (
            Objective(
                "first",
                "First",
                frozenset({"story:first"}),
                Specialist.INTERACTION,
            ),
        )
    )


def _raw(
    *,
    hp: int = 180,
    hyper_potions: int = 0,
    poke_balls: int = 0,
) -> RawGameState:
    bag = tuple(
        (int(item), quantity)
        for item, quantity in (
            (ItemId.HYPER_POTION, hyper_potions),
            (ItemId.POKE_BALL, poke_balls),
        )
        if quantity
    )
    return RawGameState(
        game_started=True,
        map_id=1,
        player_x=2,
        player_y=3,
        party_count=1,
        battle_state=0,
        bag_item_ids=tuple(item for item, _quantity in bag),
        bag_items=bag,
        party_species_ids=(0x1C,),
        party_levels=(55,),
        party_hp=(hp,),
        party_max_hp=(180,),
        party_status=(0,),
        party_moves=((57, 58, 55, 0),),
        party_pp=((15, 10, 5, 0),),
    )


class _Reader:
    def __init__(self, *, raw: RawGameState, ready: bool) -> None:
        self.raw = raw
        self.ready = ready
        self.pokedex = RedPokedexState(frozenset({9}), frozenset({9}))
        self.boxes = RedBoxCollectionState(
            tuple(RedCurrentBoxState(index, (), ()) for index in range(12)),
            0,
            False,
        )

    def read(self) -> RawGameState:
        return self.raw

    def read_pokedex_state(self) -> RedPokedexState:
        return self.pokedex

    def read_all_box_states(self) -> RedBoxCollectionState:
        return self.boxes

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0 if self.ready else 1, 0, 0, 0, 0)


class _Observer:
    def observe_raw(self, _raw: RawGameState) -> GameState:
        return GameState(GameMode.OVERWORLD, frozenset(), "test")

    def observe(self) -> GameState:
        return self.observe_raw(_raw())


class _ActionPort:
    def __init__(self, reader: _Reader) -> None:
        self.reader = reader
        self.frame_count = 100
        self.pressed_buttons = frozenset()

    def execute(self, action: MacroAction) -> MacroAction:
        self.frame_count += action.repeat
        if action.kind is MacroActionKind.CANCEL:
            self.reader.ready = True
        return action

    def read_u8(self, _address: int) -> int:
        return 0


def _adapter(reader: _Reader) -> PokemonRedGoalStateAdapter:
    return PokemonRedGoalStateAdapter(reader, _Observer(), _graph())


def test_control_recovery_is_available_only_at_a_blocked_nonbattle_boundary() -> None:
    reader = _Reader(raw=_raw(), ready=False)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedControlRecoveryGoalProvider(
        actions,
        reader,  # type: ignore[arg-type]
        port,
        adapter,
        wait_attempts=1,
        cancel_attempts=1,
        confirm_attempts=1,
        settle_frames=1,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert report.actions_executed == 3
    assert verdict.status.value == "succeeded"
    assert reader.ready

    second = provider.offer(adapter.observe())
    assert second.binding is None
    assert second.kind is GoalKind.RECOVER_CONTROL


def test_field_restore_consumes_declared_item_and_verifies_fresh_party_state(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    reader = _Reader(raw=_raw(hp=100, hyper_potions=1), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)

    def recover(
        received_actions,
        _reader,
        _emulator,
        party_index: int,
        item: ItemId,
    ) -> None:  # type: ignore[no-untyped-def]
        assert party_index == 0
        assert item is ItemId.HYPER_POTION
        received_actions.execute(MacroAction(MacroActionKind.WAIT))
        reader.raw = replace(
            reader.raw,
            bag_item_ids=(),
            bag_items=(),
            party_hp=(180,),
        )

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills.use_field_recovery_item",
        recover,
    )
    provider = RedFieldRestoreGoalProvider(
        actions,
        reader,  # type: ignore[arg-type]
        port,
        adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    assert offer.binding.opportunity.availability is GoalAvailability.AVAILABLE
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert report.actions_executed == 1
    assert verdict.status.value == "succeeded"
    assert reader.raw.party_hp == (180,)


def test_field_restore_masks_damage_when_the_required_item_is_absent() -> None:
    reader = _Reader(raw=_raw(hp=100), ready=True)
    port = _ActionPort(reader)
    adapter = _adapter(reader)
    provider = RedFieldRestoreGoalProvider(
        CountingExecutor(port),
        reader,  # type: ignore[arg-type]
        port,
        adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is None
    assert offer.kind is GoalKind.RESTORE_TEAM


class _CenterPort(_ActionPort):
    def execute(self, action: MacroAction) -> MacroAction:
        self.frame_count += action.repeat
        if action.kind is MacroActionKind.MOVE and action.value == "up":
            assert self.reader.raw.player_y is not None
            self.reader.raw = replace(
                self.reader.raw,
                player_y=self.reader.raw.player_y - 1,
            )
        elif action.kind is MacroActionKind.CONFIRM and self.reader.raw.player_y == 3:
            self.reader.raw = replace(
                self.reader.raw,
                party_hp=self.reader.raw.party_max_hp,
                party_status=(0,),
                party_pp=((15, 10, 5, 0),),
            )
        return action


def test_center_restore_reaches_nurse_and_verifies_whole_party_recovery() -> None:
    reader = _Reader(
        raw=replace(
            _raw(hp=100),
            map_id=MapId.CELADON_POKECENTER,
            player_x=3,
            player_y=7,
        ),
        ready=True,
    )
    port = _CenterPort(reader)
    provider = RedCenterRestoreGoalProvider(
        CountingExecutor(port),
        reader,  # type: ignore[arg-type]
        port,
        _adapter(reader),
        settle_frames=1,
    )

    offer = provider.offer(_adapter(reader).observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert reader.raw.player_y == 3
    assert reader.raw.party_hp == reader.raw.party_max_hp


class _MartPort(_ActionPort):
    def read_u8(self, address: int) -> int:
        if address == RamAddress.TOP_MENU_ITEM_X:
            return 5
        if address == RamAddress.TOP_MENU_ITEM_Y:
            return 4
        return 0


def test_mart_resupply_proves_balanced_resources_and_exact_economy(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    reader = _Reader(
        raw=replace(
            _raw(hyper_potions=1, poke_balls=1),
            map_id=MapId.VIRIDIAN_MART,
            player_x=2,
            player_y=4,
            player_money=5_000,
        ),
        ready=True,
    )
    port = _MartPort(reader)
    actions = CountingExecutor(port)
    prices = {int(ItemId.POKE_BALL): 200, int(ItemId.POTION): 300}

    def buy(
        received_actions,
        _emulator,
        _timing,
        *,
        absolute_index: int,
        item: int,
        quantity: int,
        target_bag_quantity: int,
    ) -> None:  # type: ignore[no-untyped-def]
        assert absolute_index in {0, 1}
        inventory = dict(reader.raw.bag_items or ())
        inventory[item] = target_bag_quantity
        assert reader.raw.player_money is not None
        reader.raw = replace(
            reader.raw,
            bag_item_ids=tuple(inventory),
            bag_items=tuple(inventory.items()),
            player_money=reader.raw.player_money - prices[item] * quantity,
        )
        received_actions.execute(MacroAction(MacroActionKind.WAIT))

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills._buy_mart_item",
        buy,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills._close_menus",
        lambda received_actions, _reader, _timing: received_actions.execute(
            MacroAction(MacroActionKind.CANCEL)
        ),
    )
    provider = RedMartResupplyGoalProvider(
        map_id=MapId.VIRIDIAN_MART,
        player_x=2,
        player_y=4,
        interaction_direction="up",
        purchases=(
            RedMartPurchase(0, ItemId.POKE_BALL, 3, 200),
            RedMartPurchase(1, ItemId.POTION, 2, 300),
        ),
        actions=actions,
        reader=reader,  # type: ignore[arg-type]
        emulator=port,
        adapter=_adapter(reader),
        wait_frames=1,
    )

    offer = provider.offer(_adapter(reader).observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert dict(reader.raw.bag_items or ()) == {
        int(ItemId.HYPER_POTION): 1,
        int(ItemId.POKE_BALL): 4,
        int(ItemId.POTION): 2,
    }
    assert reader.raw.player_money == 3_800
    assert report.evidence["money_spent"] == 1_200


def _internal_species_id(national_number: int) -> int:
    for internal in range(1, 191):
        try:
            if red_internal_species_number(internal) == national_number:
                return internal
        except ValueError:
            continue
    raise AssertionError(f"no internal species id for {national_number}")


class _AreaExecutor:
    def __init__(
        self,
        reader: _Reader,
        actions: CountingExecutor,
        source_id: str = "wild:Route1:grass",
    ) -> None:
        self.reader = reader
        self.actions = actions
        self.source_id = source_id
        self.encountered: str | None = None

    def read_collection(self):  # type: ignore[no-untyped-def]
        return red_collection_observation(
            self.reader.pokedex,
            party_observation_from_raw(self.reader.raw),
            self.reader.boxes,
        )

    def encountered_species_ref(self) -> str | None:
        return self.encountered

    def seek_encounter(self) -> None:
        survey = summarize_red_area_survey(
            self.source_id,
            self.read_collection(),
        )
        self.encountered = survey.missing_species_refs[0]
        self.actions.execute(MacroAction(MacroActionKind.WAIT))

    def capture_encounter(self, species_ref: str) -> bool:
        assert species_ref == self.encountered
        national = red_species_number(species_ref)
        boxes = list(self.reader.boxes.boxes)
        current = boxes[self.reader.boxes.current_box_index]
        boxes[current.box_index] = RedCurrentBoxState(
            current.box_index,
            (*current.species_ids, _internal_species_id(national)),
            (*current.levels, 3),
        )
        self.reader.boxes = RedBoxCollectionState(
            tuple(boxes),
            self.reader.boxes.current_box_index,
            True,
        )
        self.reader.pokedex = RedPokedexState(
            self.reader.pokedex.owned_species.union({national}),
            self.reader.pokedex.seen_species.union({national}),
        )
        self.encountered = None
        self.actions.execute(MacroAction(MacroActionKind.WAIT))
        return True

    def flee_encounter(self) -> None:
        self.encountered = None

    def switch_box(self, _box_index: int) -> None:
        raise AssertionError("Route 1 fixture has storage room")


class _DiscoveryExecutor(_AreaExecutor):
    def seek_encounter(self) -> None:
        super().seek_encounter()
        assert self.encountered is not None
        national = red_species_number(self.encountered)
        self.reader.pokedex = RedPokedexState(
            self.reader.pokedex.owned_species,
            self.reader.pokedex.seen_species.union({national}),
        )

    def flee_encounter(self) -> None:
        assert self.encountered is not None
        self.encountered = None
        self.actions.execute(MacroAction(MacroActionKind.WAIT))


def test_area_survey_provider_captures_and_independently_reloads_collection() -> None:
    reader = _Reader(raw=_raw(poke_balls=20), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=_AreaExecutor(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
        policy=RedAreaExecutionPolicy(
            max_actions=20,
            max_encounters=20,
            capture_in_requirement_order=True,
        ),
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "succeeded"
    assert report.evidence["captures"] >= 2
    assert not summarize_red_area_survey(
        "wild:Route1:grass",
        adapter.observe().collection_observation,
    ).missing_species_refs


@pytest.mark.parametrize("unsafe", [False, True])
def test_area_survey_labels_verified_no_find_without_claiming_success(unsafe) -> None:
    reader = _Reader(raw=_raw(poke_balls=20), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)

    class ExhaustedArea(_AreaExecutor):
        def seek_encounter(self):
            self.actions.execute(MacroAction(MacroActionKind.WAIT))
            raise RedAreaExecutionError("bounded search", reason_code="survey_leg_limit_exceeded")

    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass", area_executor=ExhaustedArea(reader, actions),
        actions=actions, emulator=port, adapter=adapter,
    )
    offer = provider.offer(adapter.observe())
    assert offer.binding is not None
    report = offer.binding.execute()
    if unsafe:
        reader.ready = False
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "failed"
    assert verdict.failure_reason is (
        GoalFailureReason.OUTCOME_NOT_VERIFIED if unsafe else GoalFailureReason.SEARCH_EXHAUSTED
    )
    assert report.evidence["search_exhausted"] is True
    assert report.evidence["captures"] == 0
    assert report.evidence["encounters_seen"] == 0
    assert (
        report.evidence["initial_missing_specimens"] == report.evidence["final_missing_specimens"]
    )
    assert report.actions_executed == 1
    assert report.frames_executed > 0


def test_area_survey_verifies_one_required_duplicate_precursor() -> None:
    reader = _Reader(raw=_raw(poke_balls=20), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    source_id = "wild:Route14:grass"
    before_survey = summarize_red_area_survey(
        source_id,
        adapter.observe().collection_observation,
    )
    normalizations = 0

    def normalize_after_capture() -> None:
        nonlocal normalizations
        normalizations += 1
        actions.execute(MacroAction(MacroActionKind.WAIT))

    provider = RedAreaSurveyGoalProvider(
        source_id=source_id,
        area_executor=_AreaExecutor(reader, actions, source_id),
        actions=actions,
        emulator=port,
        adapter=adapter,
        boundary=lambda _observation: RedGoalSkillAvailability.available(),
        normalize_after_capture=normalize_after_capture,
        policy=RedAreaExecutionPolicy(
            max_actions=20,
            max_encounters=20,
            capture_in_requirement_order=True,
            capture_quota=1,
        ),
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    survey = summarize_red_area_survey(
        source_id,
        adapter.observe().collection_observation,
    )
    assert verdict.status.value == "succeeded"
    assert normalizations == 1
    assert report.evidence["captures"] == 1
    assert report.evidence["source_normalized"] is True
    assert report.evidence["initial_missing_specimens"] == before_survey.missing_specimen_count
    assert report.evidence["final_missing_specimens"] == before_survey.missing_specimen_count - 1
    assert survey.missing_species_refs[0] == red_species_ref(17)


def test_area_survey_reserves_master_ball_for_nonordinary_targets() -> None:
    reader = _Reader(
        raw=replace(
            _raw(),
            bag_item_ids=(int(ItemId.MASTER_BALL),),
            bag_items=((int(ItemId.MASTER_BALL), 1),),
        ),
        ready=True,
    )
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=_AreaExecutor(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is None
    assert offer.kind is GoalKind.ACQUIRE_SPECIES


def test_encounter_discovery_learns_a_new_sighting_without_capturing() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedEncounterDiscoveryGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=_DiscoveryExecutor(reader, actions),
        actions=actions,
        emulator=port,
        adapter=adapter,
        maximum_seek_steps=4,
        maximum_encounters=2,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    assert offer.binding.verify(report).status.value == "succeeded"
    assert report.evidence == {
        "bounded": True,
        "encounters_seen": 1,
        "new_sighting_count": 1,
        "captures": 0,
    }
    assert reader.pokedex.owned_species == frozenset({9})
    assert len(reader.pokedex.seen_species) == 2


def test_box_switch_provider_requires_and_verifies_more_active_headroom(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    reader = _Reader(raw=_raw(), ready=True)
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
    boxes = list(reader.boxes.boxes)
    boxes[0] = RedCurrentBoxState(0, (0x1C,) * 19, (55,) * 19)
    reader.boxes = RedBoxCollectionState(tuple(boxes), 0, True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills.open_bills_pc",
        lambda _actions, _reader: None,
    )

    def perform_switch(
        received_actions,
        _reader,
        *,
        target_box_index: int,
    ):  # type: ignore[no-untyped-def]
        received_actions.execute(MacroAction(MacroActionKind.WAIT))
        reader.boxes = RedBoxCollectionState(reader.boxes.boxes, target_box_index, True)
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills.switch_box",
        perform_switch,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills._close_menus",
        lambda _actions, _reader, _timing: None,
    )
    provider = RedBoxSwitchGoalProvider(
        target_box_index=1,
        pc_boundary=lambda _observation: True,
        actions=actions,
        reader=reader,  # type: ignore[arg-type]
        emulator=port,
        adapter=adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "succeeded"
    assert adapter.observe().immediate_capture_slots == 20


class _RouteWorld:
    def __init__(self, reader: _Reader) -> None:
        self.reader = reader
        self.frame_count = 0
        self.pressed_buttons = frozenset()
        self.at = (2, 3)

    def execute(self, action: MacroAction) -> MacroAction:
        self.frame_count += 1
        if action.kind is MacroActionKind.MOVE:
            assert action.value == "right"
            self.at = (3, 3)
            self.reader.raw = replace(self.reader.raw, player_x=3, player_y=3)
            self.reader.pokedex = RedPokedexState(
                self.reader.pokedex.owned_species,
                self.reader.pokedex.seen_species.union({10}),
            )
        return action

    def observe(self) -> TraversalSnapshot:
        return TraversalSnapshot(1, self.at, True)

    def read_u8(self, _address: int) -> int:
        return 0


def test_route_goal_executes_only_an_acknowledged_plan_and_verifies_terminal() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    world = _RouteWorld(reader)
    actions = CountingExecutor(world)
    adapter = _adapter(reader)
    edge = LocalEdge((3, 3), "right")
    plan = RoutePlan(
        macro_path=MacroPath((1,), ()),
        start_at=(2, 3),
        start_mode=None,
        segments=(),
        terminal_approach=LocalPath(
            ((2, 3), (3, 3)),
            (edge,),
            (None, None),
        ),
        terminal_at=(3, 3),
        terminal_mode=None,
    )
    provider = RedRouteGoalProvider(
        destination_ref="local-unseen-boundary",
        plan=plan,
        actions=actions,
        traversal_observer=world,
        emulator=world,
        adapter=adapter,
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is not None
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert verdict.status.value == "succeeded"
    assert report.evidence["acknowledged_steps"] == 1
    assert world.at == (3, 3)


@dataclass
class _ProgressAdapter:
    current: object
    graph: QuestGraph

    def observe(self):  # type: ignore[no-untyped-def]
        return self.current


@pytest.mark.parametrize(
    "kind",
    (
        GoalKind.DEVELOP_TEAM,
        GoalKind.EVOLVE_SPECIES,
        GoalKind.RESTORE_TEAM,
        GoalKind.RESUPPLY,
        GoalKind.EXPLORE,
    ),
)
def test_progress_provider_requires_fresh_semantic_improvement(kind: GoalKind) -> None:
    reader = _Reader(raw=_raw(), ready=True)
    before = _adapter(reader).observe()
    evidence = before.evidence
    if kind is GoalKind.DEVELOP_TEAM:
        after_evidence = replace(
            evidence,
            team_readiness=min(1.0, evidence.team_readiness + 0.1),
        )
    elif kind is GoalKind.EVOLVE_SPECIES:
        after_evidence = replace(
            evidence,
            evolution=CompletionProgress(
                evidence.evolution.completed + 1,
                evidence.evolution.target,
            ),
        )
    elif kind is GoalKind.RESTORE_TEAM:
        evidence = replace(evidence, safety=0.5)
        before = replace(before, evidence=evidence)
        after_evidence = replace(evidence, safety=1.0)
    elif kind is GoalKind.RESUPPLY:
        after_evidence = replace(evidence, resources=0.5)
    else:
        after_evidence = replace(
            evidence,
            world_knowledge=CompletionProgress(
                evidence.world_knowledge.completed + 1,
                evidence.world_knowledge.target,
            ),
        )
    after = replace(before, evidence=after_evidence)
    adapter = _ProgressAdapter(before, _graph())

    def execute() -> GoalExecutionReport:
        adapter.current = after
        return GoalExecutionReport(1, 1, {"bounded": True})

    provider = RedProgressGoalProvider(
        kind=kind,
        binding_ref=f"pokemon.red:test:{kind.value}",
        adapter=adapter,  # type: ignore[arg-type]
        boundary=lambda _observation: RedGoalSkillAvailability.available(),
        executor=execute,
        estimated_effort=0.1,
        estimated_risk=0.1,
    )

    offer = provider.offer(before)
    assert offer.binding is not None
    assert offer.binding.verify(offer.binding.execute()).status.value == "succeeded"


def test_red_encounter_source_development_offer_is_action_free_and_verified() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    adapter = _adapter(reader)
    executions = 0

    def execute() -> GoalExecutionReport:
        nonlocal executions
        executions += 1
        reader.raw = replace(reader.raw, party_levels=(56,))
        return GoalExecutionReport(3, 90, {"bounded": True, "completed_battles": 1})

    provider = RedEncounterSourceDevelopmentGoalProvider(
        source_ref="encounter-source-fixture",
        binding_ref="pokemon.red:development:encounter-source-fixture",
        adapter=adapter,
        boundary=lambda _observation: RedGoalSkillAvailability.available(),
        executor=execute,
    )

    offer = provider.offer(adapter.observe())

    assert executions == 0
    assert offer.binding is not None
    assert offer.binding.kind is GoalKind.DEVELOP_TEAM
    verdict = offer.binding.verify(offer.binding.execute())
    assert executions == 1
    assert verdict.status.value == "succeeded"


def test_red_encounter_source_development_preserves_unavailable_boundary() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    adapter = _adapter(reader)
    provider = RedEncounterSourceDevelopmentGoalProvider(
        source_ref="encounter-source-fixture",
        binding_ref="pokemon.red:development:encounter-source-fixture",
        adapter=adapter,
        boundary=lambda _observation: RedGoalSkillAvailability.unavailable(
            GoalUnavailableReason.MISSING_CAPABILITY
        ),
        executor=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
    )

    offer = provider.offer(adapter.observe())

    assert offer.binding is None
    assert offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY


@pytest.mark.parametrize("invalid_boundary", (None, True, "available"))
def test_red_encounter_source_development_rejects_invalid_boundary_evidence(
    invalid_boundary: object,
) -> None:
    reader = _Reader(raw=_raw(), ready=True)
    adapter = _adapter(reader)
    provider = RedEncounterSourceDevelopmentGoalProvider(
        source_ref="encounter-source-fixture",
        binding_ref="pokemon.red:development:encounter-source-fixture",
        adapter=adapter,
        boundary=lambda _observation: invalid_boundary,  # type: ignore[arg-type,return-value]
        executor=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
    )

    with pytest.raises(RedGoalSkillError, match="invalid boundary evidence"):
        provider.offer(adapter.observe())


def test_red_encounter_source_development_rejects_invalid_fresh_boundary() -> None:
    reader = _Reader(raw=_raw(), ready=True)
    adapter = _adapter(reader)
    boundary_calls = 0

    def boundary(_observation: object) -> RedGoalSkillAvailability | object:
        nonlocal boundary_calls
        boundary_calls += 1
        if boundary_calls == 1:
            return RedGoalSkillAvailability.available()
        return "invalid-fresh-boundary"

    provider = RedEncounterSourceDevelopmentGoalProvider(
        source_ref="encounter-source-fixture",
        binding_ref="pokemon.red:development:encounter-source-fixture",
        adapter=adapter,
        boundary=boundary,  # type: ignore[arg-type]
        executor=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
    )
    offer = provider.offer(adapter.observe())
    assert offer.binding is not None

    with pytest.raises(RedGoalSkillError, match="invalid fresh boundary evidence"):
        offer.binding.verify(offer.binding.execute())
