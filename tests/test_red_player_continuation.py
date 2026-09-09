from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import run_paired_red_bounded_player as runner
from test_red_player_checkpoint import _complete
from test_red_player_checkpoint import case as checkpoint_case

from pokemon_red_completion.executor import ReadOnlyController
from pokemon_red_completion.red_player_checkpoint import (
    RedPlayerCheckpointError,
    capture_red_player_terminal,
    publish_red_player_checkpoint,
)

case = checkpoint_case


@pytest.mark.parametrize("feature_version", [2, 3])
def test_history_tracking_starts_only_for_explicit_successor_and_preserves_parent(feature_version):
    readiness = SimpleNamespace(continuation=None, causal_record=None)
    assert runner._execution_search_memory(readiness) is None
    readiness.causal_record = SimpleNamespace(model=SimpleNamespace(feature_version=1))
    assert runner._execution_search_memory(readiness) is None
    readiness.causal_record.model.feature_version = feature_version
    memory = runner._execution_search_memory(readiness)
    assert memory.private_dict()["entries"] == {}
    memory.record("source", "a" * 64, exhausted=True, actions=30, frames=600)
    readiness.continuation = SimpleNamespace(search_memory=memory.private_dict())
    restored = runner._execution_search_memory(readiness)
    assert restored is not memory and restored.private_dict() == memory.private_dict()
    assert restored.lookup("source", "a" * 64).exhausted == 1
    assert restored.lookup("different", "a" * 64).attempts == 0


@pytest.mark.parametrize("history_mode", ["legacy", "new", "retained"])
def test_preflight_observer_receives_actor_history_without_mutating_parent(
    monkeypatch, history_mode,
):
    from pokemon_red_completion.goal_search_memory import GoalSearchMemory

    memory = GoalSearchMemory()
    memory.record("grass", "a" * 64, exhausted=True, actions=17, frames=500)
    saved = memory.private_dict()
    readiness = SimpleNamespace(
        rom_path=Path("unused"), capture=SimpleNamespace(state_bytes=b"state"),
        continuation=SimpleNamespace(search_memory=saved) if history_mode == "retained" else None,
        causal_record=SimpleNamespace(model=SimpleNamespace(
            feature_version=1 if history_mode == "legacy" else 3,
        )),
        profile=None, quote_resource_costs=True, completion_dose=True,
        routed_recovery=True, pair_id="preview", challenger_arm_id="test",
        remaining_acquisition_demand=True, level_evolution_acquisitions=True,
        trainer_funding=True, trainer_pending_recovery=True,
        regional_trainer_funding=True,
    )
    order = []

    class Emulator:
        frame_count = 0
        pressed_buttons = ()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def load_state_bytes(self, state):
            assert state == b"state"

    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *_args, **_kwargs: Emulator())
    monkeypatch.setattr(runner, "rom_adjacent_artifacts", lambda _path: ())
    monkeypatch.setattr(runner, "_challenger_authority", lambda _ready: object())
    monkeypatch.setattr(runner, "_route_world", lambda _ready: None)
    monkeypatch.setattr(
        runner, "_verify_continuation_restore", lambda *_args: order.append("restore"),
    )
    monkeypatch.setattr(runner, "build_red_goal_context_runtime", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "PokemonRedStateReader", lambda _controller: None)
    observer = SimpleNamespace(search_memory="not wired")
    def preview_observer(*_args, **kwargs):
        assert kwargs["remaining_acquisition_demand"] is True
        assert kwargs["level_evolution_acquisitions"] is True
        assert kwargs["trainer_funding"] is True
        assert kwargs["trainer_pending_recovery"] is True
        assert kwargs["regional_trainer_funding"] is True
        return observer
    monkeypatch.setattr(runner, "_player_observer", preview_observer)

    def preflight(**kwargs):
        assert order == ["restore"]
        assert kwargs["observe"] is observer
        actual = observer.search_memory
        if history_mode == "legacy":
            assert actual is None
        else:
            assert isinstance(actual, GoalSearchMemory)
            known = actual.lookup("grass", "a" * 64)
            assert known.attempts == (1 if history_mode == "retained" else 0)
            if history_mode == "retained":
                assert (known.exhausted, known.actions, known.frames) == (1, 17, 500)
            actual.record("grass", "a" * 64, exhausted=False, actions=2, frames=10)
        return SimpleNamespace(choices=(), public_dict=lambda: {})

    monkeypatch.setattr(runner, "preflight_red_bounded_player", preflight)
    assert runner._action_free_preflight(readiness)["status"] == "ready_for_forced_bridge"
    assert saved == memory.private_dict()



@pytest.mark.parametrize("ready,battle,acts", [
    (True, False, False), (False, False, False), (True, True, False), (True, False, True),
])
def test_checkpoint_boundary_requires_action_free_ready_overworld(ready, battle, acts):
    count = [0]

    def observe():
        count[0] += int(acts)
        return SimpleNamespace(input_ready=ready, raw=SimpleNamespace(battle_state=battle))

    runtime = SimpleNamespace(adapter=SimpleNamespace(observe=observe),
                              profile=SimpleNamespace(providers=()),
                              emulator=SimpleNamespace(pressed_buttons=frozenset()))
    meter = SimpleNamespace(checkpoint=lambda: count[0])
    if ready and not battle and not acts:
        runner._require_safe_checkpoint_boundary(runtime, meter)
    else:
        with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="unsafe_boundary"):
            runner._require_safe_checkpoint_boundary(runtime, meter)


def _readiness(store, arguments):
    return runner._Readiness(
        pair_id="continuation-child", source_commit="1" * 40,
        source_bundle_sha256="2" * 64, rom_path=Path("unused"),
        rom_sha256=arguments["rom_sha256"], capture=arguments["parent"],
        profile=SimpleNamespace(profile_sha256=arguments["profile_sha256"]),
        challenger_arm_id=runner.CAUSAL_ARM_ID, legacy_model=None, causal_record=None,
        calibration_record=None, model_file_sha256="3" * 64, model_sha256="4" * 64,
        decision_limit=4, private_root=store, output_path=Path("unused-output"),
        protected_paths=(), context_origin="training", save_terminal_checkpoints=True,
    )


def _completed(case, split=None):
    store, arguments, observation = case
    document = capture_red_player_terminal(**arguments)
    _complete(store, document, alter_header={"split": split or {
        "partition": "train", "root_lineage_id": "original-training-root",
    }})
    record = publish_red_player_checkpoint(store, document)
    return _readiness(store, arguments), (arguments["episode_id"], record["record_sha256"])


def test_continuation_changes_state_not_lineage_or_partition(case):
    readiness, ancestor = _completed(case)
    continued = runner._continue_readiness(readiness, (ancestor,))
    assert continued.capture.state_bytes == b"actual-terminal-state"
    assert continued.capture.state_bytes != readiness.capture.state_bytes
    assert continued.continuation_root_lineage_id == "original-training-root"
    assert continued.training_plan is None
    assert runner._continuation_header(continued) == {
        "continuation_chain": [{
            "episode_id": ancestor[0], "checkpoint_record_sha256": ancestor[1],
        }],
        "split": {"partition": "train", "root_lineage_id": "original-training-root"},
        "independent_root": False, "training_eligible": False,
    }
    continued.continuation.require_restored_observation(case[2])


@pytest.mark.parametrize("parent_mode", [False, True])
def test_recovery_restore_mode_is_taken_from_recorded_parent_not_successor(case, parent_mode):
    store, arguments, _observation = case
    document = capture_red_player_terminal(**arguments)
    _complete(store, document, alter_header={
        "split": {"partition": "train", "root_lineage_id": "original-training-root"},
        "routed_recovery": parent_mode,
    })
    record = publish_red_player_checkpoint(store, document)
    readiness = replace(_readiness(store, arguments), routed_recovery=not parent_mode)
    resumed = runner._continue_readiness(
        readiness, ((arguments["episode_id"], record["record_sha256"]),),
    )
    assert resumed.restore_routed_recovery is parent_mode
    assert resumed.routed_recovery is not parent_mode


@pytest.mark.parametrize("partition", ["development", "validation", "test", "unassigned"])
def test_continuation_never_relabels_other_partitions(case, partition):
    readiness, ancestor = _completed(case, {"partition": partition, "root_lineage_id": "foreign"})
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="training_lineage"):
        runner._continue_readiness(readiness, (ancestor,))


@pytest.mark.parametrize("parent_mode", [False, True])
def test_remaining_demand_restores_parent_mode_and_forbids_rollback(case, parent_mode):
    store, arguments, _ = case
    document = capture_red_player_terminal(**arguments)
    _complete(store, document, alter_header={
        "split": {"partition": "train", "root_lineage_id": "original-training-root"},
        **({"remaining_acquisition_demand": True} if parent_mode else {}),
    })
    record = publish_red_player_checkpoint(store, document)
    ready = replace(_readiness(store, arguments), remaining_acquisition_demand=True)
    chain = ((arguments["episode_id"], record["record_sha256"]),)
    resumed = runner._continue_readiness(ready, chain)
    assert resumed.restore_remaining_acquisition_demand is parent_mode
    assert resumed.remaining_acquisition_demand is True
    if parent_mode:
        with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="demand_rollback"):
            runner._continue_readiness(replace(ready, remaining_acquisition_demand=False), chain)


@pytest.mark.parametrize("value", [None, 0, "true", []])
def test_invalid_checkpoint_demand_mode_cannot_change_observation(value):
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="parent_remaining"):
        runner._checkpoint_remaining_acquisition_demand({
            "metadata": {"remaining_acquisition_demand": value},
        })


@pytest.mark.parametrize("parent_mode", [False, True])
def test_level_alternatives_restore_parent_mode_and_forbid_rollback(case, parent_mode):
    store, arguments, _ = case
    document = capture_red_player_terminal(**arguments)
    _complete(store, document, alter_header={
        "split": {"partition": "train", "root_lineage_id": "original-training-root"},
        **({"remaining_acquisition_demand": True, "level_evolution_acquisitions": True}
           if parent_mode else {}),
    })
    record = publish_red_player_checkpoint(store, document)
    ready = replace(_readiness(store, arguments), remaining_acquisition_demand=True,
                    level_evolution_acquisitions=True)
    chain = ((arguments["episode_id"], record["record_sha256"]),)
    resumed = runner._continue_readiness(ready, chain)
    assert resumed.restore_level_evolution_acquisitions is parent_mode
    assert resumed.level_evolution_acquisitions is True
    if parent_mode:
        with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="acquisitions_rollback"):
            runner._continue_readiness(replace(ready, level_evolution_acquisitions=False), chain)


@pytest.mark.parametrize("metadata", [
    {"level_evolution_acquisitions": value, "remaining_acquisition_demand": True}
    for value in (None, 0, "true", [])
] + [{"level_evolution_acquisitions": True}])
def test_level_alternative_metadata_rejects_nonboolean_or_missing_demand(metadata):
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="parent_level"):
        runner._checkpoint_level_evolution_acquisitions({"metadata": metadata})


def test_old_checkpoint_does_not_gain_level_alternatives():
    assert runner._checkpoint_level_evolution_acquisitions({"metadata": {}}) is False


def test_continuation_rejects_changed_hash_duplicate_and_wrong_parent(case):
    readiness, ancestor = _completed(case)
    with pytest.raises(RedPlayerCheckpointError, match="absent or changed"):
        runner._continue_readiness(readiness, ((ancestor[0], "0" * 64),))
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="duplicate"):
        runner._continue_readiness(readiness, (ancestor, ancestor))
    continued = runner._continue_readiness(readiness, (ancestor,))
    with pytest.raises(RedPlayerCheckpointError, match="parent or scope"):
        runner._continue_readiness(continued, (ancestor,))


def test_two_saved_segments_retain_the_first_lineage(case):
    readiness, ancestor = _completed(case)
    first = runner._continue_readiness(readiness, (ancestor,))
    store, arguments, _ = case
    arguments["emulator"].state = b"second-terminal-state"
    second_document = capture_red_player_terminal(**{
        **arguments, "parent": first.capture, "episode_id": "second-parent",
    })
    _complete(store, second_document, alter_header=runner._continuation_header(first))
    second_record = publish_red_player_checkpoint(store, second_document)
    chain = (ancestor, ("second-parent", second_record["record_sha256"]))
    second = runner._continue_readiness(readiness, chain)
    assert second.capture.state_bytes == b"second-terminal-state"
    assert second.continuation_chain == chain
    assert second.continuation_root_lineage_id == "original-training-root"


def test_expansion_preserves_original_restore_and_can_continue_expanded_child(case):
    readiness, ancestor = _completed(case)
    expanded = SimpleNamespace(profile_sha256="e" * 64)
    first = runner._continue_readiness(readiness, (ancestor,), expanded_profile=expanded)
    assert first.restore_profile is readiness.profile
    assert first.profile is expanded
    store, arguments, _ = case
    child = capture_red_player_terminal(**{
        **arguments, "parent": first.capture, "episode_id": "expanded-parent",
        "profile_sha256": expanded.profile_sha256,
    })
    _complete(store, child, alter_header=runner._continuation_header(first))
    record = publish_red_player_checkpoint(store, child)
    resumed = runner._continue_readiness(
        readiness, (ancestor, ("expanded-parent", record["record_sha256"])),
        expanded_profile=expanded,
    )
    assert resumed.restore_profile is expanded
    assert resumed.profile is expanded
    assert resumed.continuation_root_lineage_id == "original-training-root"


def test_training_continuation_binds_actual_saved_state_not_original_bytes(case):
    from test_goal_resource_quote import _supply_model
    from test_red_player_training import _plan

    from pokemon_red_completion.red_player_training_dataset import _require_continuation_origin
    from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan

    readiness, ancestor = _completed(case)
    continued = runner._continue_readiness(readiness, (ancestor,))
    original = RedPlayerTrainingPlan({
        **_plan(_supply_model()).document, "root_lineage_id": "original-training-root",
    })
    plan = runner.continue_red_player_training(
        original, capture=continued.capture, root_lineage_id="original-training-root",
        episode_id=ancestor[0], checkpoint_sha256=ancestor[1],
        restore_profile_sha256=readiness.profile.profile_sha256,
        execution_profile_sha256="e" * 64,
    )
    assert plan.document["state_sha256"] == continued.capture.state_sha256
    assert plan.document["origin_state_sha256"] == original.document["state_sha256"]
    assert plan.document["profile_sha256"] == "e" * 64
    assert plan.document["restore_profile_sha256"] == readiness.profile.profile_sha256
    _require_continuation_origin(readiness.private_root, plan)
    for field in ("root_lineage_id", "state_sha256", "restore_profile_sha256",
                  "continuation_checkpoint_sha256"):
        changed = RedPlayerTrainingPlan({
            **plan.document, field: "foreign-root" if field == "root_lineage_id" else "0" * 64,
        })
        with pytest.raises(ValueError, match="continued training"):
            _require_continuation_origin(readiness.private_root, changed)


def test_boxed_profile_transition_verifies_old_save_before_new_execution(case):
    readiness, ancestor = _completed(case)
    original = readiness.profile
    evolution = SimpleNamespace(profile_sha256="f" * 64)
    continued = runner._continue_readiness(readiness, (ancestor,), execution_profile=evolution)
    assert continued.restore_profile is original
    assert continued.profile is evolution
    assert continued.continuation_root_lineage_id == "original-training-root"


def test_regional_chain_preserves_restore_profile_and_rejects_history_rollback(case):
    readiness, ancestor = _completed(case)
    first_profile = SimpleNamespace(profile_sha256="a" * 64)
    second_profile = SimpleNamespace(profile_sha256="b" * 64)
    first = runner._continue_readiness(
        readiness, (ancestor,), regional_profiles=(first_profile,),
    )
    assert first.restore_profile is readiness.profile
    assert first.profile is first_profile
    store, arguments, _ = case
    child = capture_red_player_terminal(**{
        **arguments, "parent": first.capture, "episode_id": "regional-parent",
        "profile_sha256": first_profile.profile_sha256,
    })
    _complete(store, child, alter_header=runner._continuation_header(first))
    record = publish_red_player_checkpoint(store, child)
    chain = (ancestor, ("regional-parent", record["record_sha256"]))
    resumed = runner._continue_readiness(
        readiness, chain, regional_profiles=(first_profile, second_profile),
    )
    assert resumed.restore_profile is first_profile
    assert resumed.profile is second_profile
    assert resumed.continuation_root_lineage_id == "original-training-root"
    with pytest.raises(RedPlayerCheckpointError):
        runner._continue_readiness(readiness, chain, regional_profiles=(second_profile,))
    rollback = capture_red_player_terminal(**{
        **arguments, "parent": resumed.capture, "episode_id": "regional-rollback",
    })
    _complete(store, rollback, alter_header=runner._continuation_header(resumed))
    rollback_record = publish_red_player_checkpoint(store, rollback)
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="profile_rollback"):
        runner._continue_readiness(
            readiness, (*chain, ("regional-rollback", rollback_record["record_sha256"])),
            regional_profiles=(first_profile, second_profile),
        )
    revisited = runner._continue_readiness(
        readiness, (*chain, ("regional-rollback", rollback_record["record_sha256"])),
        regional_profiles=(first_profile, second_profile, readiness.profile),
    )
    assert revisited.restore_profile is readiness.profile
    assert revisited.profile is readiness.profile
    assert len(revisited.continuation_chain) == 3


@pytest.mark.parametrize("damage", [None, "semantics", "frames", "held"])
def test_actual_restore_is_checked_through_readonly_controls(case, monkeypatch, damage):
    readiness, ancestor = _completed(case)
    readiness = runner._continue_readiness(readiness, (ancestor,))
    original_profile = readiness.profile
    readiness = replace(
        readiness, profile=SimpleNamespace(profile_sha256="e" * 64), routed_recovery=True,
        remaining_acquisition_demand=True, level_evolution_acquisitions=True,
        trainer_funding=True, trainer_pending_recovery=True,
        regional_trainer_funding=True,
    )
    emulator = SimpleNamespace(frame_count=12, pressed_buttons=frozenset())
    seen = []

    def runtime(**kwargs):
        assert isinstance(kwargs["emulator"], ReadOnlyController)
        assert kwargs["profile"] is original_profile
        seen.append("readonly")
        return object()

    def observe():
        seen.append("observe")
        if damage == "frames":
            emulator.frame_count += 1
        if damage == "held":
            emulator.pressed_buttons = frozenset({"a"})
        return (
            replace(case[2], semantic_state_sha256="0" * 64)
            if damage == "semantics" else case[2]
        )

    monkeypatch.setattr(runner, "build_red_goal_context_runtime", runtime)
    monkeypatch.setattr(runner, "_route_world", lambda _: None)
    def player_observer(*_args, completion_dose=False, routed_recovery=False,
                        trainer_funding=False, trainer_pending_recovery=False,
                        regional_trainer_funding=False,
                        remaining_acquisition_demand=False, level_evolution_acquisitions=False):
        assert completion_dose is False  # This historical fixture predates completion dose.
        assert routed_recovery is False
        assert trainer_funding is False
        assert trainer_pending_recovery is False
        assert regional_trainer_funding is False
        assert remaining_acquisition_demand is False  # Never use successor mode for old restore.
        assert level_evolution_acquisitions is False
        return observe

    monkeypatch.setattr(runner, "_player_observer", player_observer)
    if damage is None:
        runner._verify_continuation_restore(readiness, emulator)
    else:
        with pytest.raises((RedPlayerCheckpointError, runner.PairedRedBoundedPlayerRunError)):
            runner._verify_continuation_restore(readiness, emulator)
    assert seen == ["readonly", "observe"]


@pytest.mark.parametrize("override", [
    {"context_origin": "development"},
    {"save_terminal_checkpoints": False}, {"challenger": runner.BASELINE_ARM_ID},
])
def test_unsupported_continuation_scope_fails_before_source_or_rom(override):
    args = SimpleNamespace(
        pair_id="new-continuation", continue_from_checkpoint=[("old", "a" * 64)],
        **{
            "train_player": False, "context_origin": "training",
            "save_terminal_checkpoints": True, "challenger": runner.CAUSAL_ARM_ID,
            **override,
        },
    )
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="continuation_scope"):
        runner._prepare(args)


def test_training_continuation_passes_scope_but_still_requires_source_check(monkeypatch):
    args = SimpleNamespace(
        pair_id="sampled-continuation", continue_from_checkpoint=[("old", "a" * 64)],
        train_player=True, context_origin="training", save_terminal_checkpoints=True,
        challenger=runner.CAUSAL_ARM_ID, expand_local_development=True,
    )

    def source(*_a, **_k):
        raise RuntimeError("source verification reached")

    monkeypatch.setattr(runner, "detect_source_identity", source)
    with pytest.raises(RuntimeError, match="source verification reached"):
        runner._prepare(args)


@pytest.mark.parametrize("sources,routed", [
    ([str(i) for i in range(513)], True),
    ([None], True), (["wild:Route2:grass"], False),
])
def test_regional_scope_rejects_bad_declarations_before_source_or_rom(sources, routed):
    args = SimpleNamespace(
        pair_id="regional-scope", continue_from_checkpoint=[("old", "a" * 64)],
        challenger=runner.CAUSAL_ARM_ID, context_origin="training",
        save_terminal_checkpoints=True, wild_source=sources, routed_resource_goals=routed,
    )
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="regional_profile_scope"):
        runner._prepare(args)


@pytest.mark.parametrize("count", [9, 32, 33, 512])
def test_extended_regional_history_keeps_explicit_transitions_bounded(count, monkeypatch):
    args = SimpleNamespace(
        pair_id="regional-long-history", continue_from_checkpoint=[("old", "a" * 64)],
        train_player=True, challenger=runner.CAUSAL_ARM_ID, context_origin="training",
        save_terminal_checkpoints=True,
        regional_transitions=["wild:Route4:grass"] * count, routed_resource_goals=True,
    )
    def source(*_a, **_k):
        raise RuntimeError("source verification reached")
    monkeypatch.setattr(runner, "detect_source_identity", source)
    with pytest.raises(RuntimeError, match="source verification reached"):
        runner._prepare(args)


def test_regional_builder_uses_cartridge_edges_and_keeps_nonwild_provider(monkeypatch):
    from test_red_living_dex_wild_corridor import _graph, _terrain

    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.red_goal_context_profile import (
        RedGoalMechanic,
        build_red_goal_context_profile_payload,
        parse_red_goal_context_profile,
    )
    from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        RedLivingDexWildCorridorError,
        derive_red_living_dex_wild_corridor,
    )
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="regional-builder", providers=(
            (GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
             corridor.profile_parameters()),
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
            (GoalKind.EXPLORE, RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
             corridor.profile_parameters()),
        ),
    ))
    world = SimpleNamespace(terrain={13: _terrain()}, local_graphs={13: _graph()},
                            object_blockers={13: frozenset({(3, 1)})}, rom=b"fixture")
    monkeypatch.setattr(runner, "_route_world", lambda _: world)
    built, = runner._regional_profiles(profile, ("wild:Route2:grass",), object())
    assert built.providers[0].parameters["player_x"] == 4
    assert built.providers[1] == profile.providers[1]
    from pokemon_red_completion import gen1_cartridge as cartridge
    monkeypatch.setattr(cartridge, "internal_to_dex", lambda _: {90: 16, 91: 21})
    monkeypatch.setattr(cartridge, "wild_tables", lambda _, **kw: {13: [(3, 90), (5, 91)]})
    expanded, moved = runner._regional_profiles(
        profile, ("opportunistic-capture", "wild:Route2:grass"), object(),
    )
    assert expanded.providers[0].parameters["capture_species_numbers"] == (16, 21)
    assert moved.providers[0].parameters["capture_species_numbers"] == (16, 21)
    assert "capture_species_numbers" not in profile.providers[0].parameters
    world.local_graphs[13] = _graph(one_way=True)
    with pytest.raises(RedLivingDexWildCorridorError, match="no unobstructed"):
        runner._regional_profiles(profile, ("wild:Route2:grass",), object())


@pytest.mark.parametrize("source", ["wild:SafariZoneCenter:grass", "wild:UnknownMap:grass"])
def test_regional_builder_rejects_special_capture_rules_before_cartridge(source, monkeypatch):
    def world(_):
        raise AssertionError("must reject unsupported mechanics before cartridge access")
    monkeypatch.setattr(runner, "_route_world", world)
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="ordinary_wild_capture"):
        runner._regional_profiles(object(), (source,), object())


def test_regional_transition_parser_preserves_interleaved_source_supply_order():
    args = runner._parser().parse_args([
        "--pair-id", "parse-only", "--state", "state", "--envelope", "envelope",
        "--profile", "profile", "--private-artifact-root", "private", "--out", "out",
        "--wild-source", "wild:Route11:grass", "--supply-profile", "shop.json",
        "--wild-source", "wild:Route24:grass",
        "--discovery-source", "wild:Route24:grass",
        "--capture-status-support",
        "--opportunistic-capture",
        "--affordable-capture-supply",
        "--evolution-objective", "63:64:16",
        "--evolution-fly-transport",
    ])
    assert args.regional_transitions == [
        "wild:Route11:grass", Path("shop.json"), "wild:Route24:grass",
        "discovery:wild:Route24:grass",
        "capture-status",
        "opportunistic-capture",
        "affordable-capture-supply",
        "evolution:63:64:16",
        "evolution-fly",
    ]


@pytest.mark.parametrize("value", ["63:64", "63:64:16:1", "0:64:16", "63:63:16",
                                        "63:64:101", "63:64:-1", "true:64:16"])
def test_future_evolution_argument_rejects_malformed_targets(value):
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        runner._evolution_objective_argument(value)


def test_fly_modifier_is_ordered_after_old_profiles_without_changing_them(monkeypatch):
    from test_red_goal_context_profile import _supply_transition_profile

    before = runner._boxed_evolution_profile(_supply_transition_profile(), (96, 97, 26))
    monkeypatch.setattr(runner, "_route_world", lambda _: object())
    old_hash = before.profile_sha256
    (future,) = runner._regional_profiles(before, ("evolution-fly",), object())
    assert before.profile_sha256 == old_hash
    old = next(s for s in before.providers if s.kind.value == "evolve_species")
    new = next(s for s in future.providers if s.kind.value == "evolve_species")
    assert "fly_transport" not in old.parameters
    assert dict(new.parameters) == {**dict(old.parameters), "fly_transport": True}
    assert [s for s in before.providers if s.kind.value != "evolve_species"] == [
        s for s in future.providers if s.kind.value != "evolve_species"
    ]


def test_future_evolution_preserves_historical_supply_profiles(monkeypatch):
    from test_red_goal_context_profile import _supply_transition_profile

    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.observation import ItemId, MapId
    from pokemon_red_completion.red_goal_context_profile import RedGoalContextProfileError

    before = runner._boxed_evolution_profile(_supply_transition_profile(), (77, 78, 40))
    supplied = runner._boxed_evolution_profile(
        _supply_transition_profile(MapId.CERULEAN_MART, ItemId.POKE_BALL), (77, 78, 40),
    )
    previous_hashes = before.profile_sha256, supplied.profile_sha256
    source = Path("private-supply.json")
    monkeypatch.setattr(runner, "_route_world", lambda _: object())
    monkeypatch.setattr(runner, "_regular_external", lambda path, **_: path)
    monkeypatch.setattr(runner, "load_red_goal_context_profile", lambda _: supplied)
    ready = SimpleNamespace(rom_path=Path("private-cartridge"))
    old, future = runner._regional_profiles(before, (source, "evolution:63:64:16"), ready)
    assert old == supplied and old.profile_sha256 == previous_hashes[1]
    assert before.profile_sha256 == previous_hashes[0]
    evolution = next(s for s in future.providers if s.kind is GoalKind.EVOLVE_SPECIES)
    assert dict(evolution.parameters) == {
        "source_species_ref": "pokemon:national:063", "target_species_ref": "pokemon:national:064",
        "evolution_level": 16,
    }
    assert tuple(s for s in old.providers if s.kind is not GoalKind.EVOLVE_SPECIES) == tuple(
        s for s in future.providers if s.kind is not GoalKind.EVOLVE_SPECIES
    )
    # Moving the future change before an old supply profile must still fail.
    with pytest.raises(RedGoalContextProfileError, match="non-supply skill"):
        runner._regional_profiles(before, ("evolution:63:64:16", source), ready)


def test_regional_supply_loads_private_profile_and_rejects_non_supply_change(monkeypatch):
    from test_red_goal_context_profile import _supply_transition_profile

    from pokemon_red_completion.observation import ItemId, MapId
    from pokemon_red_completion.red_goal_context_profile import RedGoalContextProfileError
    before = _supply_transition_profile()
    after = _supply_transition_profile(MapId.CERULEAN_MART, ItemId.POKE_BALL)
    source = Path("private-supply.json")
    seen = []
    monkeypatch.setattr(runner, "_route_world", lambda _: object())
    monkeypatch.setattr(runner, "_regular_external",
                        lambda path, **kw: seen.append((path, kw["subject"])) or path)
    monkeypatch.setattr(runner, "load_red_goal_context_profile", lambda path: after)
    ready = SimpleNamespace(rom_path=Path("private-cartridge"))
    assert runner._regional_profiles(before, (source,), ready) == (after,)
    assert seen == [(source, "supply_profile")]
    monkeypatch.setattr(runner, "load_red_goal_context_profile",
                        lambda path: replace(after, profile_id="foreign"))
    with pytest.raises(RedGoalContextProfileError, match="manager contract"):
        runner._regional_profiles(before, (source,), ready)


def test_regional_discovery_transition_uses_world_rom_and_current_profile(monkeypatch):
    from pokemon_red_completion import red_living_dex_wild_corridor as corridor
    before, after = object(), object()
    monkeypatch.setattr(runner, "_route_world", lambda _: SimpleNamespace(rom=b"verified-world"))
    seen = []
    def bind(profile, source, rom):
        seen.append((profile, source, rom))
        return after
    monkeypatch.setattr(corridor, "bind_red_local_discovery_profile", bind)
    assert runner._regional_profiles(
        before, ("discovery:wild:Route24:grass",), object(),
    ) == (after,)
    assert seen == [(before, "wild:Route24:grass", b"verified-world")]


def test_continuation_executes_only_one_arm_without_fit_or_comparison(case, monkeypatch):
    readiness, ancestor = _completed(case)
    readiness = runner._continue_readiness(readiness, (ancestor,))
    arm_calls, writes = [], []
    # Checkpoint publishing itself is covered by the live-arm wiring test.
    readiness = replace(readiness, save_terminal_checkpoints=False)
    monkeypatch.setattr(runner, "_prepare", lambda _: readiness)
    monkeypatch.setattr(runner, "rom_adjacent_artifacts", lambda _: {})
    monkeypatch.setattr(runner, "_action_free_preflight", lambda _: {"actions": 0})
    monkeypatch.setattr(runner, "_challenger_authority", lambda _: object())

    def execute(_readiness, *, arm_id, **_kwargs):
        arm_calls.append(arm_id)
        return SimpleNamespace(
            trajectory_manifest_sha256="a" * 64,
            episode=SimpleNamespace(public_dict=lambda: {"completed_test_steps": 4}),
        )

    monkeypatch.setattr(runner, "_run_arm", execute)
    monkeypatch.setattr(runner, "compare_paired_bounded_player_arms", lambda **_: pytest.fail(
        "continuation unexpectedly compared against a replay"
    ))
    monkeypatch.setattr(runner, "_write_exclusive", lambda _, value: writes.append(value))
    result = runner._run(SimpleNamespace())
    assert arm_calls == [runner.CAUSAL_ARM_ID]
    assert result["model_fitted"] is False
    assert result["training_eligible"] is False
    assert result["independent_evaluation"] is False
    assert result["split"]["root_lineage_id"] == "original-training-root"
    assert writes == [result]


def test_live_arm_refuses_input_on_restore_mismatch(case, monkeypatch):
    readiness, ancestor = _completed(case)
    readiness = runner._continue_readiness(readiness, (ancestor,))
    order = []

    class Emulator:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            order.append("closed")

        def load_state_bytes(self, state):
            assert state == b"actual-terminal-state"
            order.append("loaded")

    def reject(_readiness, _emulator):
        order.append("verified")
        raise RedPlayerCheckpointError("restored checkpoint semantic state differs")

    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *_a, **_k: Emulator())
    monkeypatch.setattr(runner, "_verify_continuation_restore", reject)
    monkeypatch.setattr(runner, "WindowedFrameBudgetController", lambda *_a, **_k: pytest.fail(
        "controller became available before checkpoint agreement"
    ))
    with pytest.raises(RedPlayerCheckpointError, match="semantic state differs"):
        runner._run_arm(readiness, arm_id=runner.CAUSAL_ARM_ID, authority=object())
    assert order == ["loaded", "verified", "closed"]
    state = readiness.private_root.inspect_episode_state("continuation-child-causal")
    assert state.status != "absent"
