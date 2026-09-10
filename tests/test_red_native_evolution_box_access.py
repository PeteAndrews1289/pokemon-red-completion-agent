from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context import _ActionDelegate
from test_red_native_boxed_evolution import runtime_fixture
from test_red_resource_goal_router import _World

import pokemon_red_completion.red_native_evolution_box_access as access
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_collection import RedCurrentBoxState, red_internal_species_id
from pokemon_red_completion.red_goal_context import _RedTeamGoalProvider
from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution
from pokemon_red_completion.route_executor import TraversalSnapshot


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    runtime, reader, _ = runtime_fixture(
        tmp_path, source=11, target=12, evolution_level=10, level=4
    )
    reader.boxes = replace(reader.boxes, current_box_index=1, storage_initialized=True)
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_evolution.wild_tables",
        lambda _: {22: [(10, 0x21)]},
    )
    world = _World()
    native = bind_native_boxed_evolution(runtime, world, allow_cross_box=True)
    actions = CountingExecutor(_ActionDelegate())
    provider = native.provider_for(GoalKind.EVOLVE_SPECIES, actions)
    observation = native.adapter.observe()
    request = provider._boxed_evolution_request(observation)
    traversal = SimpleNamespace(
        observe=lambda: TraversalSnapshot(
            int(reader.raw.map_id), (reader.raw.player_y, reader.raw.player_x), True
        )
    )
    route = world.plan_feasible_to_map(traversal.observe(), int(reader.raw.map_id), goal_at=(4, 13))
    calls = []

    def tick(count, frames):
        actions.actions_executed += count
        native.emulator.frame_count += frames

    def travel(*args, **kwargs):
        calls.append("travel")
        tick(7, 50)
        reader.raw = replace(reader.raw, player_x=13, player_y=4)
        return SimpleNamespace(passed=True)

    def face(*args):
        calls.append("face")
        tick(1, 1)

    def open_pc(*args):
        calls.append("open")
        tick(1, 2)

    def switch(*args, target_box_index):
        calls.append(("switch", target_box_index))
        tick(3, 30)
        reader.boxes = replace(reader.boxes, current_box_index=target_box_index)
        return SimpleNamespace(passed=True)

    def close(*args):
        calls.append("close")
        tick(1, 4)

    monkeypatch.setattr(access, "execute_route", travel)
    monkeypatch.setattr(access, "face_pc_boundary", face)
    monkeypatch.setattr(access, "open_bills_pc", open_pc)
    monkeypatch.setattr(access, "switch_box", switch)
    monkeypatch.setattr(access, "close_menu", close)
    return SimpleNamespace(
        runtime=native,
        reader=reader,
        world=world,
        actions=actions,
        request=request,
        traversal=traversal,
        route=route,
        calls=calls,
        run=lambda: access.prepare_evolution_box(native, world, actions, traversal, route, request),
    )


def test_cross_box_is_opt_in_and_offer_does_not_rotate(fixture):
    f = fixture
    old = bind_native_boxed_evolution(f.runtime, f.world)
    assert (
        old.provider_for(GoalKind.EVOLVE_SPECIES, f.actions).offer(old.adapter.observe()).binding
        is None
    )
    assert (
        f.runtime.provider_for(GoalKind.EVOLVE_SPECIES, f.actions)
        .offer(f.runtime.adapter.observe())
        .binding
        is not None
    )
    assert f.request.current_box_index == 0
    assert f.request.precursor_box_slot == 1
    assert f.reader.boxes.current_box_index == 1
    assert f.calls == []
    assert f.actions.actions_executed == f.runtime.emulator.frame_count == 0


def test_actual_box_is_rotated_before_existing_engine_and_all_costs_retained(fixture):
    f = fixture
    before = f.runtime.adapter.observe().collection_observation
    boundary, evidence = f.run()
    assert f.calls == ["travel", "face", "open", ("switch", 0), "close"]
    assert boundary.at == (4, 13)
    assert boundary.map_id == f.reader.raw.map_id
    assert f.runtime.adapter.observe().collection_observation == replace(
        before, current_box_index=0
    )
    assert evidence == {
        "storage_preparation": {
            "box_rotations": 1,
            "collection_preserved": True,
            "setup_training_rows": 0,
            "actions_executed": 13,
            "frames_executed": 87,
        }
    }
    assert f.actions.actions_executed == 13
    assert f.runtime.emulator.frame_count == 87
    with pytest.raises(access.RedEvolutionBoxAccessError, match="before input"):
        f.run()
    assert f.actions.actions_executed == 13


@pytest.mark.parametrize("mutation", ["source", "deposit", "battle", "full", "disabled", "route"])
def test_stale_or_unsupported_request_fails_before_input(fixture, mutation):
    f = fixture
    if mutation == "source":
        f.reader.boxes = replace(
            f.reader.boxes,
            boxes=(
                RedCurrentBoxState(0, (red_internal_species_id(14),) * 2, (4, 4)),
                *f.reader.boxes.boxes[1:],
            ),
        )
    elif mutation == "deposit":
        f.reader.raw = replace(
            f.reader.raw, party_species_ids=(*f.reader.raw.party_species_ids[:5], 1)
        )
    elif mutation == "battle":
        f.reader.raw = replace(f.reader.raw, battle_state=1)
    elif mutation == "full":
        f.reader.boxes = replace(
            f.reader.boxes,
            boxes=(
                RedCurrentBoxState(0, (red_internal_species_id(11),) * 20, (4,) * 20),
                *f.reader.boxes.boxes[1:],
            ),
        )
    elif mutation == "disabled":
        f.runtime.boxed_level_evolution_cross_box = False
    else:
        f.route = f.world.plan_feasible_to_map(
            f.traversal.observe(), int(f.reader.raw.map_id), goal_at=(4, 12)
        )
    with pytest.raises((access.RedEvolutionBoxAccessError, ValueError)):
        access.prepare_evolution_box(f.runtime, f.world, f.actions, f.traversal, f.route, f.request)
    assert f.calls == []
    assert f.actions.actions_executed == f.runtime.emulator.frame_count == 0


@pytest.mark.parametrize(
    "mutation",
    ["wrong_box", "lost_specimen", "level", "money", "party", "false_report", "boundary"],
)
def test_rotation_must_preserve_real_state_not_just_report_success(fixture, monkeypatch, mutation):
    f = fixture
    original = access.switch_box

    def switch(*args, **kwargs):
        result = original(*args, **kwargs)
        if mutation == "wrong_box":
            f.reader.boxes = replace(f.reader.boxes, current_box_index=2)
        elif mutation in {"lost_specimen", "level"}:
            box = f.reader.boxes.boxes[0]
            box = (
                replace(box, species_ids=box.species_ids[:1], levels=box.levels[:1])
                if mutation == "lost_specimen"
                else replace(box, levels=(5, 4))
            )
            f.reader.boxes = replace(f.reader.boxes, boxes=(box, *f.reader.boxes.boxes[1:]))
        elif mutation == "money":
            f.reader.raw = replace(f.reader.raw, player_money=f.reader.raw.player_money - 1)
        elif mutation == "party":
            f.reader.raw = replace(f.reader.raw, party_hp=(149, *f.reader.raw.party_hp[1:]))
        elif mutation == "boundary":
            f.reader.raw = replace(f.reader.raw, player_x=12)
        elif mutation == "false_report":
            return SimpleNamespace(passed=False)
        return result

    monkeypatch.setattr(access, "switch_box", switch)
    with pytest.raises(access.RedEvolutionBoxAccessError, match="did not preserve"):
        f.run()


def test_request_prefers_current_box_then_actual_box_and_slot(fixture):
    f = fixture
    # Different boxes and slots must compete; a single populated box cannot
    # distinguish current-box preference from a hardcoded box-zero selection.
    source = red_internal_species_id(11)
    other = red_internal_species_id(19)
    boxes = list(f.reader.boxes.boxes)
    boxes[0] = RedCurrentBoxState(0, (source,), (4,))
    boxes[2] = RedCurrentBoxState(2, (other, source), (8, 4))
    f.reader.boxes = replace(f.reader.boxes, boxes=tuple(boxes), current_box_index=2)
    spec = next(s for s in f.runtime.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)
    provider = _RedTeamGoalProvider(f.runtime, spec, f.actions)
    request = provider._boxed_evolution_request(f.runtime.adapter.observe())
    assert (request.current_box_index, request.precursor_box_slot) == (2, 2)
    f.reader.boxes = replace(f.reader.boxes, current_box_index=3)
    assert provider._boxed_evolution_request(f.runtime.adapter.observe()).current_box_index == 0


@pytest.mark.parametrize("target,current", [(7, 3), (11, 0)])
def test_box_access_uses_actual_nonzero_target(fixture, target, current):
    f = fixture
    boxes = list(f.reader.boxes.boxes)
    boxes[target] = replace(boxes[0], box_index=target)
    boxes[0] = RedCurrentBoxState(0, (), ())
    f.reader.boxes = replace(f.reader.boxes, boxes=tuple(boxes), current_box_index=current)
    provider = f.runtime.provider_for(GoalKind.EVOLVE_SPECIES, f.actions)
    request = provider._boxed_evolution_request(f.runtime.adapter.observe())
    assert request.current_box_index == target
    access.prepare_evolution_box(f.runtime, f.world, f.actions, f.traversal, f.route, request)
    assert ("switch", target) in f.calls
    assert f.reader.boxes.current_box_index == target


def test_failed_approach_never_opens_pc(fixture, monkeypatch):
    f = fixture
    monkeypatch.setattr(access, "execute_route", lambda *_, **kw: SimpleNamespace(passed=False))
    with pytest.raises(access.RedEvolutionBoxAccessError, match="approach"):
        f.run()
    assert f.calls == []


def test_replan_cannot_add_field_actions(fixture, monkeypatch):
    from pokemon_red_completion.actions import MacroActionKind

    f = fixture
    invalid = SimpleNamespace(
        steps=(replace(f.route.steps[0], action_kind=MacroActionKind.FIELD_MOVE, action="surf"),)
    )
    monkeypatch.setattr(type(f.world), "replanner", lambda _: lambda request: invalid)

    def travel(*args, replanner, **kwargs):
        replanner(None)
        raise AssertionError("unsupported replan accepted")

    monkeypatch.setattr(access, "execute_route", travel)
    with pytest.raises(access.RedEvolutionBoxAccessError, match="unsupported field"):
        f.run()
    assert f.calls == []


def test_native_executor_composes_actual_box_access_with_existing_engine(fixture, monkeypatch):
    import pokemon_red_completion.red_native_boxed_evolution as native_module
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
    from pokemon_red_completion.red_boxed_level_evolution import ObservedSemanticBoundaryBinding

    f = fixture
    monkeypatch.setattr(native_module, "Gen1TraversalObserver", lambda _: f.traversal)
    monkeypatch.setattr(native_module, "finish_center_dialogue", lambda *_: None)
    received = []

    def engine(**kwargs):
        assert f.reader.boxes.current_box_index == 0
        assert isinstance(kwargs["route_to_pc"], ObservedSemanticBoundaryBinding)
        assert kwargs["route_to_pc"].at == f.traversal.observe().at == (4, 13)
        assert kwargs["route_to_training"].plan.start_at == (4, 13)
        received.append(kwargs)

        def execute(request, actions):
            assert request == f.request
            assert actions is f.actions
            actions.actions_executed += 7
            f.runtime.emulator.frame_count += 20
            return GoalExecutionReport(7, 20, {"bounded": True})

        return execute

    monkeypatch.setattr(native_module, "RedGoalBoxedEvolutionExecutor", engine)
    provider = f.runtime.provider_for(GoalKind.EVOLVE_SPECIES, f.actions)
    offered = provider.offer(f.runtime.adapter.observe())
    assert f.calls == []
    report = offered.binding.execute()
    assert len(received) == 1
    assert report.actions_executed == f.actions.actions_executed == 20
    assert report.frames_executed == f.runtime.emulator.frame_count == 107
    assert report.evidence["storage_preparation"]["setup_training_rows"] == 0
    # The stub engine did not evolve anything: PC success must not be goal success.
    assert offered.binding.verify(report).status.value == "failed"
