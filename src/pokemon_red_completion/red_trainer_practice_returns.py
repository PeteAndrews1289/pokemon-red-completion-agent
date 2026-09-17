"""Frozen whole-party outcome target for executed TRAIN battle branches.

No teacher choice, inferred unplayed action, policy latency, or emulator frame
count enters this reward. Frames and PP remain separately measurable costs.
Every sibling branch is scored with the same coefficients and turn horizon.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

RETURN_SCHEMA_ID = "pokemon.red.trainer-practice.whole-party-return.v1"
TIE_EPSILON = 0.02


class TrainerPracticeReturnError(ValueError):
    """An episode lacks the observed resources needed for a common return."""


@dataclass(frozen=True, slots=True)
class TrainerPracticeReturn:
    value: float
    terminal: float
    opponent_faints: int
    party_faints: int
    opponent_damage_fraction: float
    party_damage_fraction: float
    pp_spent_fraction: float
    frames_executed: int
    player_turn_count: int
    truncated: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RETURN_SCHEMA_ID,
            **{
                name: getattr(self, name)
                for name in (
                    "value",
                    "terminal",
                    "opponent_faints",
                    "party_faints",
                    "opponent_damage_fraction",
                    "party_damage_fraction",
                    "pp_spent_fraction",
                    "frames_executed",
                    "player_turn_count",
                    "truncated",
                )
            },
        }


def score_trainer_practice_episode(episode: Mapping[str, object]) -> TrainerPracticeReturn:
    """Score all attack, switch, prompt, and forced-replacement consequences."""

    decisions = episode.get("decisions")
    metrics = episode.get("metrics")
    if not isinstance(decisions, list) or not decisions or not isinstance(metrics, Mapping):
        raise TrainerPracticeReturnError("executed trainer decisions are missing")
    initial = decisions[0]
    if not isinstance(initial, Mapping):
        raise TrainerPracticeReturnError("initial trainer decision differs")
    initial_state = initial.get("state_before")
    if not isinstance(initial_state, Mapping):
        raise TrainerPracticeReturnError("initial resource state is missing")
    initial_caps = _integers(initial_state.get("party_max_hp"), positive=True)
    initial_pp = _pp_total(initial_state.get("party_pp"))
    total_cap = sum(initial_caps)
    party_lost = 0
    opponent_damage = 0.0
    for decision in decisions:
        if not isinstance(decision, Mapping):
            raise TrainerPracticeReturnError("trainer decision differs")
        before, after = decision.get("state_before"), decision.get("state_after")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise TrainerPracticeReturnError("trainer resource chain is missing")
        before_hp = _integers(before.get("party_hp"))
        after_hp = _integers(after.get("party_hp"))
        if len(before_hp) != len(after_hp) or len(before_hp) != len(initial_caps):
            raise TrainerPracticeReturnError("trainer party resources differ")
        party_lost += sum(
            max(0, start - end) for start, end in zip(before_hp, after_hp, strict=True)
        )
        enemy_before, enemy_after = (
            decision.get("opponent_hp_before"),
            decision.get("opponent_hp_after"),
        )
        observation = decision.get("observation")
        if not isinstance(observation, Mapping):
            raise TrainerPracticeReturnError("opponent observation is missing")
        features = observation.get("features")
        battle = features.get("battle") if isinstance(features, Mapping) else None
        enemy_cap = battle.get("opponent_max_hp") if isinstance(battle, Mapping) else None
        if (
            type(enemy_before) is not int
            or type(enemy_after) is not int
            or type(enemy_cap) is not int
            or enemy_cap <= 0
            or not 0 <= enemy_before <= enemy_cap
            or enemy_after < 0
        ):
            raise TrainerPracticeReturnError("opponent HP evidence is invalid")
        # A replacement opponent may have less HP than the one just defeated.
        # Its HP is not damage dealt to the defeated species.
        decision_faints = _nonnegative(decision.get("opponent_faints", 0))
        if decision_faints and enemy_after > 0:
            opponent_damage += enemy_before / enemy_cap
        elif enemy_after <= enemy_before:
            opponent_damage += (enemy_before - enemy_after) / enemy_cap
    stop = episode.get("stop_reason")
    terminal = 3.0 if stop == "battle_won" else -3.0 if stop == "party_defeated" else 0.0
    if stop not in {"battle_won", "party_defeated", "player_turn_budget"}:
        raise TrainerPracticeReturnError("trainer terminal is unsupported")
    fainted_enemy = _nonnegative(metrics.get("opponent_faints"))
    fainted_party = _nonnegative(metrics.get("party_faints"))
    spent_pp = _nonnegative(metrics.get("party_pp_spent"))
    frames = _nonnegative(episode.get("frames_executed"))
    turns = _nonnegative(episode.get("player_turn_count"))
    party_fraction = party_lost / total_cap
    pp_fraction = spent_pp / max(1, initial_pp)
    score = (
        terminal
        + fainted_enemy
        - fainted_party
        + 0.5 * opponent_damage
        - 0.75 * party_fraction
        - 0.05 * pp_fraction
    )
    return TrainerPracticeReturn(
        value=round(score, 9),
        terminal=terminal,
        opponent_faints=fainted_enemy,
        party_faints=fainted_party,
        opponent_damage_fraction=round(opponent_damage, 9),
        party_damage_fraction=round(party_fraction, 9),
        pp_spent_fraction=round(pp_fraction, 9),
        frames_executed=frames,
        player_turn_count=turns,
        truncated=stop == "player_turn_budget",
    )


def tied_best_indices(values: tuple[float, ...]) -> tuple[int, ...]:
    """Keep near-equal measured outcomes as ties, never arbitrary hard labels."""

    if not values:
        raise TrainerPracticeReturnError("return inventory is empty")
    best = max(values)
    return tuple(index for index, value in enumerate(values) if best - value <= TIE_EPSILON)


def _integers(value: object, *, positive: bool = False) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(type(number) is not int or number < (1 if positive else 0) for number in value)
    ):
        raise TrainerPracticeReturnError("party resource vector differs")
    return tuple(value)


def _pp_total(value: object) -> int:
    if (
        not isinstance(value, list)
        or not value
        or any(
            not isinstance(row, list) or any(type(pp) is not int or pp < 0 for pp in row)
            for row in value
        )
    ):
        raise TrainerPracticeReturnError("party PP inventory differs")
    return sum(sum(row) for row in value)


def _nonnegative(value: object) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise TrainerPracticeReturnError("trainer cost differs")
    return value
