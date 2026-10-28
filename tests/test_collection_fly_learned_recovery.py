"""Composition contracts for the learned handler dropped by Fly onward walking."""

from dataclasses import replace
from hashlib import sha256

import pytest

from test_red_collection_fly import scene  # shared ROM-free cartridge/menu scene
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.goal_manager import GoalKind, GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding, GoalExecutionReport, GoalRecoveryRequired, GoalVerification,
)
from pokemon_red_completion.red_player_engaged_story import EngagedStoryRouteHandler
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


@pytest.mark.parametrize('fault', [None, 'missing_binding', 'map_drift', 'unresolved'])
@pytest.mark.parametrize('fainted_slots', [1, 2])
def test_fly_retains_learned_battle_owner_and_route_proof(scene, monkeypatch, fault, fainted_slots):
    """A live faint reaches learned control, never the legacy attack fallback."""
    game = scene.game
    original_execute = game.execute
    monkeypatch.setattr(game, 'save_state_bytes', lambda: repr(game.raw).encode(), raising=False)
    wrapped = []
    calls = []

    def execute(action):
        original_execute(action)
        if action.kind is MacroActionKind.MOVE and game.stage == 'landed':
            game.raw = replace(game.raw, battle_state=2, active_party_index=0,
                               party_hp=(0,) * fainted_slots + game.raw.party_hp[fainted_slots:])

    monkeypatch.setattr(game, 'execute', execute)
    scene.observer.observe = lambda: TraversalSnapshot(
        game.raw.map_id, (game.raw.player_y, game.raw.player_x),
        game.raw.battle_state == 0 and game.read_input_readiness().ready,
        interruption='battle:2' if game.raw.battle_state else None, mode='land',
    )

    def binding_factory():
        calls.append(('binding', game.raw.party_hp))
        source_hash = sha256(game.save_state_bytes()).hexdigest()
        if fault == 'missing_binding':
            return None

        def play():
            calls.append(('learned', game.raw.party_hp))
            assert game.raw.party_hp[0] == 0 and any(game.raw.party_hp)
            scene.router.actions.execute(MacroAction(MacroActionKind.WAIT))
            game.raw = replace(game.raw, battle_state=2 if fault == 'unresolved' else 0,
                active_party_index=fainted_slots, map_id=5 if fault == 'map_drift' else game.raw.map_id)
            return GoalExecutionReport(1, 1, {
                'support': 'already_engaged_native_trainer', 'source_sha256': source_hash,
                'terminal_sha256': sha256(game.save_state_bytes()).hexdigest(), 'battle': {
                'schema': 'pokemon.red.learned-trainer-completion.v1', 'field_ready': fault != 'unresolved',
                'outcome': 'unresolved' if fault == 'unresolved' else 'won',
                'money_delta': 0, 'fainted_party_slots': list(range(1, fainted_slots + 1)),
            }})

        return ExecutableGoalBinding('pokemon.red:retained-engagement:' + source_hash,
            GoalKind.RECOVER_CONTROL, .3, .4, play, lambda _: GoalVerification.succeeded())

    def wrapper(inner, spec):
        assert spec is scene.spec and game.flight_confirms == 1
        # The fallback must not get a single trainer input, even on failure.
        inner.inner.move_slot_policy = lambda _: pytest.fail('legacy trainer attack')
        handler = EngagedStoryRouteHandler(inner, game, binding_factory)
        wrapped.append(handler)
        return handler

    scene.router.interruption_handler_wrapper = wrapper
    bound = scene.bind()
    assert not wrapped and not calls and not game.actions
    if fault:
        with pytest.raises(RouteExecutionError):
            bound.execute()
        assert scene.provider_calls == [] and not wrapped[0].trainer_evidence
    else:
        report = bound.execute()
        assert bound.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED
        assert report.evidence['route_setback']['party_hp'] == list(game.raw.party_hp)
        assert report.evidence['route_setback']['terminal_sha256'] == sha256(game.save_state_bytes()).hexdigest()
        assert report.evidence['destination_executed'] is False
        assert scene.provider_calls == []
        assert len(wrapped[0].trainer_evidence) == 1
        receipt = wrapped[0].trainer_evidence[0]
        assert receipt.details['learned_combat'] is True
        assert receipt.details['battle']['fainted_party_slots'] == list(range(1, fainted_slots + 1))
        assert game.raw.party_hp[:fainted_slots] == (0,) * fainted_slots
    assert len(wrapped) == 1 and calls[0][0] == 'binding'


def test_fly_retains_verified_blackout_without_destination_execution(scene, monkeypatch):
    """The same wrapped path keeps native cash loss and fails the selected goal."""
    game = scene.game
    original_execute = game.execute
    monkeypatch.setattr(game, 'save_state_bytes', lambda: repr(game.raw).encode(), raising=False)

    def execute(action):
        original_execute(action)
        if action.kind is MacroActionKind.MOVE and game.stage == 'landed':
            game.raw = replace(game.raw, battle_state=2)

    monkeypatch.setattr(game, 'execute', execute)
    scene.observer.observe = lambda: TraversalSnapshot(
        game.raw.map_id, (game.raw.player_y, game.raw.player_x), not game.raw.battle_state,
        interruption='battle:2' if game.raw.battle_state else None, mode='land',
    )

    def factory():
        source_hash = sha256(game.save_state_bytes()).hexdigest()
        cash = game.raw.player_money

        def play():
            scene.router.actions.execute(MacroAction(MacroActionKind.WAIT))
            game.raw = replace(game.raw, battle_state=0, player_money=cash // 2,
                               map_id=64, player_y=3, player_x=4)
            return GoalExecutionReport(1, 1, dict(
                support='already_engaged_native_trainer', source_sha256=source_hash,
                terminal_sha256=sha256(game.save_state_bytes()).hexdigest(),
                objective_completed=False, reward=None,
                battle=dict(schema='pokemon.red.learned-trainer-completion.v1',
                    outcome='lost', field_ready=True, money_delta=cash // 2 - cash)))

        return ExecutableGoalBinding('pokemon.red:retained-engagement:' + source_hash,
            GoalKind.RECOVER_CONTROL, .3, .4, play,
            lambda _: GoalVerification.failed(GoalFailureReason.RESOURCE_LOST))

    scene.router.interruption_handler_wrapper = lambda inner, spec: EngagedStoryRouteHandler(
        inner, game, factory)
    bound = scene.bind()
    report = bound.execute()
    assert bound.verify(report).status.value == 'failed'
    assert scene.provider_calls == [] and game.raw.player_money == 619 // 2
    assert game.raw.map_id == 64 and report.actions_executed > 0 and report.frames_executed > 0
