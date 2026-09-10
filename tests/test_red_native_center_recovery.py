from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context import _ActionDelegate
from test_red_native_boxed_evolution import runtime_fixture

import pokemon_red_completion.red_native_boxed_evolution as native
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification


@pytest.mark.parametrize("mutation", [None, "partial", "money", "specimen", "verifier"])
def test_newly_withdrawn_injured_member_must_be_healed_and_verified(
    tmp_path, monkeypatch, mutation
):
    runtime, reader, _ = runtime_fixture(tmp_path)
    reader.raw = replace(reader.raw, party_hp=(*reader.raw.party_hp[:5], 5))
    actions = CountingExecutor(_ActionDelegate())
    events = []
    facing = ["left"]

    def face(actions, reader, direction):
        assert direction == "up"
        events.append("face")
        facing[0] = direction
        actions.actions_executed += 2

    def heal():
        assert facing[0] == "up"
        events.append("heal")
        actions.actions_executed += 3
        if mutation != "partial":
            reader.raw = replace(reader.raw, party_hp=reader.raw.party_max_hp)
        if mutation == "money":
            reader.raw = replace(reader.raw, player_money=reader.raw.player_money - 1)
        if mutation == "specimen":
            reader.raw = replace(
                reader.raw, party_species_ids=(*reader.raw.party_species_ids[:5], 1)
            )
        return GoalExecutionReport(3, 0, {})

    def verify(report):
        events.append("verify")
        if mutation == "verifier":
            from pokemon_red_completion.goal_manager import GoalFailureReason

            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    monkeypatch.setattr("pokemon_red_completion.red_pc_storage.face_pc_boundary", face)
    monkeypatch.setattr(
        native,
        "RedCenterRestoreGoalProvider",
        lambda *_: SimpleNamespace(
            offer=lambda _: SimpleNamespace(binding=SimpleNamespace(execute=heal, verify=verify)),
        ),
    )
    if mutation is None:
        assert native.restore_native_center_party(runtime, actions) == 1
        assert reader.raw.party_hp == reader.raw.party_max_hp
    else:
        with pytest.raises(native.context.RedGoalContextError, match="heal the party"):
            native.restore_native_center_party(runtime, actions)
    assert events == ["face", "heal", "verify"]
    assert actions.actions_executed == 5


def test_healthy_party_does_not_trigger_extra_heal_or_input(tmp_path):
    runtime, _, _ = runtime_fixture(tmp_path)
    actions = CountingExecutor(_ActionDelegate())
    assert native.restore_native_center_party(runtime, actions) == 0
    assert actions.actions_executed == 0


@pytest.mark.parametrize("direction", ["up", "down", "left", "right"])
def test_real_center_provider_heals_nonlead_after_stationary_orientation(direction):
    from test_red_goal_skills import _adapter, _raw, _Reader

    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.observation import MapId

    raw = _raw()
    reader = _Reader(
        raw=replace(
            raw,
            map_id=MapId.VERMILION_POKECENTER,
            player_x=3,
            player_y=3,
            party_count=2,
            party_species_ids=(28, 124),
            party_levels=(64, 4),
            party_hp=(180, 5),
            party_max_hp=(180, 18),
            party_status=(0, 0),
            party_moves=(raw.party_moves[0], (106, 0, 0, 0)),
            party_pp=(raw.party_pp[0], (30, 0, 0, 0)),
        ),
        ready=True,
    )
    facing = [direction]
    reader.read_player_facing = lambda: facing[0]
    seen = []
    emulator = SimpleNamespace(frame_count=0)

    def execute(action):
        seen.append(action.kind)
        emulator.frame_count += action.repeat
        if action.kind is MacroActionKind.MOVE:
            assert action.value == "up"
            facing[0] = "up"  # Nurse counter blocks displacement.
        if action.kind is MacroActionKind.CONFIRM:
            assert facing[0] == "up"
            reader.raw = replace(reader.raw, party_hp=reader.raw.party_max_hp)
        return action

    actions = CountingExecutor(SimpleNamespace(execute=execute))
    runtime = SimpleNamespace(reader=reader, adapter=_adapter(reader), emulator=emulator)
    assert native.restore_native_center_party(runtime, actions) == 1
    assert reader.raw.party_hp == (180, 18)
    assert (reader.raw.player_x, reader.raw.player_y) == (3, 3)
    assert seen.count(MacroActionKind.MOVE) == (0 if direction == "up" else 1)
    assert seen.count(MacroActionKind.CONFIRM) == 1
    assert actions.actions_executed == (2 if direction == "up" else 4)
