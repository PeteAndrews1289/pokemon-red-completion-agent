"""Indoor walking retains the existing learned trainer interruption owner."""
from dataclasses import replace
from hashlib import sha256
import pytest
from test_red_indoor_collection_departure import indoor_scene
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.goal_manager import GoalKind, GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_player_engaged_story import EngagedStoryRouteHandler
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


@pytest.mark.parametrize("fault", [None, "missing_binding", "map_drift", "unresolved"])
@pytest.mark.parametrize("fainted_slots", [1, 2])
def test_indoor_exit_retains_learned_recovery_and_custody(indoor_scene, monkeypatch, fault, fainted_slots):
    scene = indoor_scene
    game = scene.game
    original_execute = game.execute
    monkeypatch.setattr(game, "save_state_bytes", lambda: repr(game.raw).encode(), raising=False)
    injected = []
    wrapped = []
    calls = []
    def execute(action):
        original_execute(action)
        if action.kind is MacroActionKind.MOVE and game.stage == "field" and not injected:
            injected.append(True)
            game.raw = replace(game.raw, battle_state=2, active_party_index=0,
                party_hp=(0,) * fainted_slots + game.raw.party_hp[fainted_slots:])
    monkeypatch.setattr(game, "execute", execute)
    scene.observer.observe = lambda: TraversalSnapshot(
        game.raw.map_id, (game.raw.player_y, game.raw.player_x),
        game.raw.battle_state == 0,
        interruption="battle:2" if game.raw.battle_state else None,
        mode="land", last_outside_map=game.last_outside_map,
    )
    def factory():
        calls.append("binding")
        if fault == "missing_binding":
            return None
        source_hash = sha256(game.save_state_bytes()).hexdigest()
        def play():
            calls.append("learned")
            assert not game.raw.party_hp[0] and any(game.raw.party_hp)
            scene.router.actions.execute(MacroAction(MacroActionKind.WAIT))
            game.raw = replace(game.raw, battle_state=2 if fault == "unresolved" else 0,
                active_party_index=fainted_slots, map_id=5 if fault == "map_drift" else game.raw.map_id)
            return GoalExecutionReport(1, 1, dict(
                support="already_engaged_native_trainer", source_sha256=source_hash,
                terminal_sha256=sha256(game.save_state_bytes()).hexdigest(),
                battle=dict(schema="pokemon.red.learned-trainer-completion.v1",
                    field_ready=fault != "unresolved", outcome="unresolved" if fault == "unresolved" else "won",
                    money_delta=0, fainted_party_slots=list(range(1, fainted_slots + 1)))))
        return ExecutableGoalBinding("pokemon.red:retained-engagement:" + source_hash,
            GoalKind.RECOVER_CONTROL, .3, .4, play, lambda _: GoalVerification.succeeded())
    def wrapper(inner, spec):
        assert spec is scene.spec and game.flight_confirms == 0
        inner.inner.move_slot_policy = lambda _: pytest.fail("legacy trainer attack")
        handler = EngagedStoryRouteHandler(inner, game, factory)
        wrapped.append(handler)
        return handler
    scene.router.interruption_handler_wrapper = wrapper
    bound = scene.bind()
    assert len(wrapped) == 1 and not calls and not game.actions
    if fault:
        with pytest.raises(RouteExecutionError):
            bound.execute()
        assert not scene.provider_calls and not wrapped[0].trainer_evidence
    else:
        report = bound.execute()
        assert bound.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED
        assert not scene.provider_calls and game.flight_confirms == 0
        assert report.evidence["destination_executed"] is False
        assert len(wrapped[0].trainer_evidence) == 1
        assert wrapped[0].trainer_evidence[0].details["learned_combat"] is True
        assert game.raw.party_hp[:fainted_slots] == (0,) * fainted_slots
    assert calls[0] == "binding"
