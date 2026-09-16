"""Durable, teacher-free move decisions within one bounded development battle.

The caller owns authenticated encounter setup and hard controller budgets. The
ranker receives only semantic features. This is experimental move authority,
not a promotion of the collection player's fixed battle controller.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from .actions import MacroAction, MacroActionKind
from .battle_model import BattleMoveScorer
from .battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    BattleActionExecutor,
    BattleRuntimeTiming,
    BattleStateReader,
    execute_bounded_battle_move_turn,
)
from .observation import BattleMenuPhase, RawGameState
from .red_autonomous_player import _record, _write
from .red_battle_scenario import prepare_red_battle_scenario, project_red_battle_turn_outcome
from .red_trajectory import PokemonRedObservationEncoder


class FrozenBattleRanker(BattleMoveScorer, Protocol):
    def to_json(self) -> str: ...


def battle_facts(raw: RawGameState) -> dict[str, object]:
    """Retain public outcome facts separately from policy-visible features."""
    return {
        "map_id": raw.map_id,
        "battle_state": raw.battle_state,
        "active_party_index": raw.active_party_index,
        "player_species": raw.active_party_species_id,
        "player_level": raw.active_party_level,
        "player_hp": raw.battler_hp,
        "player_max_hp": raw.battler_max_hp,
        "moves": raw.battler_moves,
        "pp": raw.battler_pp,
        "enemy_species": raw.enemy_species_id,
        "enemy_level": raw.enemy_level,
        "enemy_hp": raw.enemy_hp,
        "enemy_max_hp": raw.enemy_max_hp,
        "party_hp": raw.party_hp,
    }


def settle_learned_battle_boundary(
    reader: BattleStateReader,
    executor: BattleActionExecutor,
    *,
    expected_map: int,
    timing: BattleRuntimeTiming = DEFAULT_BATTLE_RUNTIME_TIMING,
) -> RawGameState:
    """Dismiss text with B; never choose FIGHT, a replacement, or a new move.

    B is harmless at a stale MAIN signature. Two stable MAIN observations
    separated by B/wait avoid treating the immediate attack effect as a fresh
    decision. Faints and unexpected menus fail closed before another input.
    """
    initial = reader.read()
    stable_main = 0
    stable_field = 0
    for _ in range(timing.max_runtime_pulses):
        raw = reader.read()
        if raw.map_id != expected_map or raw.battle_state not in {0, 1}:
            raise RuntimeError("learned battle left its declared wild encounter")
        if raw.battle_state == 0:
            if reader.read_input_readiness().ready:
                stable_field += 1
                if stable_field >= timing.required_ready_reads:
                    return raw
                executor.execute(
                    MacroAction(
                        MacroActionKind.WAIT,
                        repeat=timing.completion_wait_frames,
                    )
                )
                continue
            stable_field = 0
        else:
            if raw.battler_hp is None or raw.battler_hp <= 0:
                raise RuntimeError("learned battle stopped at a fainted or unknown lead")
            if initial.battle_state == 1 and (
                raw.active_party_index != initial.active_party_index
                or raw.battler_moves != initial.battler_moves
                or raw.battler_pp != initial.battler_pp
            ):
                raise RuntimeError("battle settling changed the battler, moves or PP")
            phase = reader.read_battle_menu_state(raw).phase
            if phase not in {BattleMenuPhase.UNKNOWN, BattleMenuPhase.MAIN}:
                raise RuntimeError("learned battle reached an unowned menu")
            stable_main = stable_main + 1 if phase is BattleMenuPhase.MAIN else 0
            if stable_main >= 2 and raw.enemy_hp is not None and raw.enemy_hp > 0:
                return raw
        executor.execute(MacroAction(MacroActionKind.CANCEL))
        executor.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_wait_frames))
    raise RuntimeError("learned battle exceeded its bounded dialogue settling")


def run_learned_battle(
    *,
    output: Path,
    reader: BattleStateReader,
    executor: BattleActionExecutor,
    encoder: PokemonRedObservationEncoder,
    model: FrozenBattleRanker,
    snapshot: Callable[[], bytes],
    costs: Callable[[], Mapping[str, int]],
    setup: Callable[[], None],
    provenance: Mapping[str, object],
    expected_map: int,
    maximum_decisions: int = 8,
    timing: BattleRuntimeTiming = DEFAULT_BATTLE_RUNTIME_TIMING,
) -> dict[str, object]:
    """Retain intent before every query, selection before every owned input.

    Incomplete directories are consumed. Any failure ends this run without a
    teacher fallback, rewind or replacement trial. Terminal retention also
    covers setup and persistence failures; storage failure propagates.
    """
    if type(maximum_decisions) is not int or not 1 <= maximum_decisions <= 8:  # noqa: E721
        raise ValueError("learned battle requires one to eight decisions")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    model_sha = hashlib.sha256(model.to_json().encode("ascii")).hexdigest()
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.learned-battle.v1",
            "model_sha256": model_sha,
            "maximum_decisions": maximum_decisions,
            "expected_map": expected_map,
            "provenance": dict(provenance),
            "teacher_battle_queries": 0,
            "teacher_battle_fallback": False,
            "development_only": True,
            "promotion": False,
            "fit_allowed": False,
        },
    )
    decisions: list[dict[str, object]] = []
    queries = 0
    reason = "decision_limit"
    error: dict[str, str] | None = None
    try:
        _write(output / "origin.state", snapshot())
        _record(output / "setup-started.json", {"costs": dict(costs())})
        setup()
        raw = settle_learned_battle_boundary(
            reader,
            executor,
            expected_map=expected_map,
            timing=timing,
        )
        _record(output / "setup-outcome.json", {"facts": battle_facts(raw), "costs": dict(costs())})
        for index in range(maximum_decisions):
            if raw.battle_state == 0:
                reason = "battle_exited"
                break
            step = output / f"step-{index:03d}"
            step.mkdir(mode=0o700)
            prepared = prepare_red_battle_scenario(encoder, raw)
            features = prepared.features
            if model.feature_names != features.feature_names:
                raise ValueError("battle model feature contract differs")
            if sum(features.legal_mask) < 2:
                reason = "no_alternatives"
                break
            before = snapshot()
            _write(step / "before.state", before)
            intent = {
                "model_sha256": model_sha,
                "observation_sha256": prepared.initial_observation_sha256,
                "state_sha256": hashlib.sha256(before).hexdigest(),
                "candidate_vectors": features.candidate_vectors,
                "legal_mask": features.legal_mask,
                "current_pp": features.current_pp,
                "slot_indices": features.slot_indices,
                "facts": battle_facts(raw),
                "query_may_be_consumed": True,
            }
            _record(step / "query-started.json", intent)
            queries += 1
            candidate = model.predict(
                features.candidate_vectors,
                legal_mask=features.legal_mask,
                current_pp=features.current_pp,
            )
            # Persist even a bad model answer before interpreting its authority.
            _record(step / "prediction.json", {"candidate_index": candidate})
            if (
                type(candidate) is not int  # noqa: E721
                or not 0 <= candidate < len(features.legal_mask)
                or not features.legal_mask[candidate]
            ):
                raise ValueError("battle model selected an illegal candidate")
            slot = features.slot_indices[candidate] + 1
            if snapshot() != before or reader.read() != raw:
                raise ValueError("battle state changed during the model decision")
            if raw.battler_moves is None:
                raise ValueError("battle move identities disappeared")
            choice = {
                "candidate_index": candidate,
                "selected_slot": slot,
                "move_id": raw.battler_moves[slot - 1],
                "observation_sha256": prepared.initial_observation_sha256,
                "model_sha256": model_sha,
            }
            _record(step / "execution-started.json", choice)
            row: dict[str, object] = {"index": index, "choice": choice}
            decisions.append(row)
            execution = execute_bounded_battle_move_turn(
                reader,
                executor,
                expected_map=expected_map,
                selected_slot=slot,
                expected_battle_state=1,
                timing=timing,
                label=f"learned encounter decision {index}",
            )
            row["immediate_outcome"] = project_red_battle_turn_outcome(execution).public_dict()
            _write(step / "after-effect.state", snapshot())
            _record(step / "effect.json", row)
            raw = settle_learned_battle_boundary(
                reader,
                executor,
                expected_map=expected_map,
                timing=timing,
            )
            row["settled_facts"] = battle_facts(raw)
            row["cumulative_costs"] = dict(costs())
            _write(step / "terminal.state", snapshot())
            _record(step / "outcome.json", row)
            if raw.battle_state == 0:
                reason = "battle_exited"
                break
            if not execution.move_executed:
                reason = "move_not_executed"
                break
    except Exception as failure:
        reason = "failed"
        error = {"type": type(failure).__name__, "message": str(failure)}
    terminal = snapshot()
    _write(output / "terminal.state", terminal)
    report: dict[str, object] = {
        "schema": "pokemon.red.learned-battle-outcome.v1",
        "stop_reason": reason,
        "error": error,
        "model_sha256": model_sha,
        "model_queries": queries,
        "decisions": decisions,
        "terminal_state_sha256": hashlib.sha256(terminal).hexdigest(),
        "terminal_facts": battle_facts(reader.read()),
        "costs": dict(costs()),
        "teacher_battle_queries": 0,
        "teacher_battle_fallbacks": 0,
        "model_updates": 0,
        "promotion": False,
        "development_only": True,
    }
    _record(output / "outcome.json", report)
    return report
