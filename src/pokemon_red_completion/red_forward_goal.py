"""Red observation adapter for a separately declared forward story target.

Only this adapter sees cartridge identities. The new learner receives current
resource ratios and the existing semantic option vectors. A final Champion goal
requires concurrent Champion and Hall-of-Fame facts, never a latched earlier flag.
No script, teacher, model selection, emulator input or historical-row conversion
is performed here. Resource units count gross decreases of declared consumables
between observed macro boundaries; they are not a claim about intra-macro trades.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .domain import GameState
from .forward_goal import (
    ForwardGoalChoice,
    ForwardGoalCounters,
    ForwardGoalOutcome,
    ForwardGoalPlan,
    ForwardGoalRecorder,
)
from .goal_manager_composition_runtime import CompositionBudgetCheckpoint, CompositionBudgetMeter
from .observation import ItemId, game_mode, semantic_facts
from .provenance import canonical_sha256
from .red_goal_manager import RedGoalObservation
from .red_pp_observation import observe_pp_resources
from .referee import CHAMPION_DEFEATED_FACT, CompletionReferee
from .route import COMPLETION_QUEST, HALL_OF_FAME_FACT

RED_FORWARD_CONTEXT_NAMES = (
    "party_hp_fraction",
    "party_pp_fraction",
    "recovery_stock_fraction",
    "pp_stock_fraction",
    "story_pressure",
    "team_pressure",
    "safety_pressure",
)
RED_FORWARD_EXECUTION_FLAGS = (
    "routed_resource_goals",
    "quote_resource_costs",
    "completion_dose",
    "routed_recovery",
    "trainer_funding",
    "trainer_pending_recovery",
    "regional_trainer_funding",
    "remaining_acquisition_demand",
    "level_evolution_acquisitions",
)
_CONSUMABLES = frozenset(
    int(item)
    for item in (
        ItemId.POKE_BALL,
        ItemId.GREAT_BALL,
        ItemId.ULTRA_BALL,
        ItemId.MASTER_BALL,
        ItemId.POTION,
        ItemId.SUPER_POTION,
        ItemId.HYPER_POTION,
        ItemId.FULL_RESTORE,
        ItemId.ANTIDOTE,
        ItemId.AWAKENING,
        ItemId.PARLYZ_HEAL,
        ItemId.FULL_HEAL,
        ItemId.REVIVE,
        ItemId.ELIXIR,
    )
)


def red_forward_goal_facts(objective_id: str) -> frozenset[str]:
    objective = COMPLETION_QUEST.objective(objective_id)
    if objective_id in {"defeat_champion", "enter_hall_of_fame"}:
        return frozenset({CHAMPION_DEFEATED_FACT, HALL_OF_FAME_FACT})
    return objective.completion_facts


def red_forward_verifier_sha256(objective_id: str) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.red.forward-story-verifier.v1",
            "objective": objective_id,
            "concurrent_facts": sorted(red_forward_goal_facts(objective_id)),
        }
    )


def red_forward_goal_observed(observation: RedGoalObservation, objective_id: str) -> bool:
    """Verify the current sample rather than a historical semantic tracker latch."""
    raw = observation.raw
    if not isinstance(raw.event_flags, bytes) or len(raw.event_flags) != 319:
        raise ValueError("forward-goal verifier requires complete current event flags")
    fresh = GameState(mode=game_mode(raw), facts=semantic_facts(raw))
    if objective_id in {"defeat_champion", "enter_hall_of_fame"}:
        return CompletionReferee().inspect(fresh).complete
    return red_forward_goal_facts(objective_id) <= fresh.facts


def red_forward_execution_flags(
    values: Mapping[str, object] | None = None,
) -> dict[str, bool]:
    """Project declared execution flags, with absent flags strictly defaulting false.

    The mapping may be a complete authenticated episode header. Unrelated fields
    are not continuation features; present capability values must be exact bools.
    Dependency and historical-rollback checks remain the runner's responsibility.
    """
    if values is None:
        values = {}
    if not isinstance(values, Mapping):
        raise ValueError("Red forward execution flags must come from a mapping")
    result = {}
    for name in RED_FORWARD_EXECUTION_FLAGS:
        enabled = values.get(name, False)
        if type(enabled) is not bool:
            raise ValueError(f"Red forward execution flag {name} must be a boolean")
        result[name] = enabled
    return result


def red_forward_continuation_sha256(
    *,
    behavior_policy_id: str,
    model_sha256: str,
    source_bundle_sha256: str,
    profile_sha256: str,
    execution_flags: Mapping[str, object] | None = None,
) -> str:
    # The episode's training plan separately binds its seed. Different seeds are
    # realizations of this same stochastic continuation, not different policies.
    return canonical_sha256(
        {
            "schema": "pokemon.red.forward-existing-policy-continuation.v1",
            "behavior_policy_id": behavior_policy_id,
            "model_sha256": model_sha256,
            "source_bundle_sha256": source_bundle_sha256,
            "profile_sha256": profile_sha256,
            "execution_flags": red_forward_execution_flags(execution_flags),
            "strategy": "same-frozen-actor-and-honest-singletons-up-to-two-macros",
        }
    )


def red_forward_context(observation: RedGoalObservation) -> tuple[float, ...]:
    """Fresh resource quantities only; no objective identity or future outcome."""
    raw = observation.raw
    if (
        raw.party_hp is None
        or raw.party_max_hp is None
        or not raw.party_count
        or (len(raw.party_hp) != raw.party_count or len(raw.party_max_hp) != raw.party_count)
        or any(
            type(hp) is not int
            or type(maximum) is not int
            or not 0 <= hp <= maximum
            or maximum <= 0
            for hp, maximum in zip(raw.party_hp, raw.party_max_hp, strict=True)
        )
    ):
        raise ValueError("forward-goal observation needs a complete current party")
    pp = observe_pp_resources(raw)
    current = sum(slot[0] for member in pp.party_slots for slot in member)
    maximum = sum(slot[1] for member in pp.party_slots for slot in member)
    if maximum <= 0:
        raise ValueError("forward-goal observation lacks usable move capacity")
    return (
        sum(raw.party_hp) / sum(raw.party_max_hp),
        current / maximum,
        observation.recovery_item_count / (observation.recovery_item_count + 8),
        pp.item_count / (pp.item_count + 1),
        observation.situation.story_pressure,
        observation.situation.team_pressure,
        observation.situation.safety_pressure,
    )


def _consumable_stock(observation: RedGoalObservation) -> dict[int, int]:
    stock: dict[int, int] = {}
    if observation.raw.bag_items is None:
        raise ValueError("forward-goal observation lacks inventory")
    for item, count in observation.raw.bag_items:
        if (
            type(item) is not int
            or not 1 <= item <= 255
            or item in stock
            or (type(count) is not int or not 1 <= count <= 99)
        ):
            raise ValueError("forward-goal inventory differs")
        stock[item] = count
    return {item: stock.get(item, 0) for item in _CONSUMABLES}


@dataclass(slots=True)
class RedForwardGoalCollector:
    """Action-free live hooks around one sampled choice and its continuation.

    The owner must restrict macros to declared story/field-restoration mechanics
    (no within-macro buying/replenishment) for boundary inventory deltas to mean
    gross spending. It must stop whenever ``outcome`` becomes non-None, and stop
    immediately on any hook failure. This class cannot release controller input.
    """

    plan: ForwardGoalPlan
    objective_id: str
    observe: Callable[[], RedGoalObservation]
    meter: CompositionBudgetMeter
    append: Callable[[dict[str, object]], None]
    recorder: ForwardGoalRecorder = field(init=False)
    _start: CompositionBudgetCheckpoint | None = field(default=None, init=False)
    _initial: RedGoalObservation | None = field(default=None, init=False)
    _stock: dict[int, int] = field(default_factory=dict, init=False)
    _spent: int = field(default=0, init=False)
    _macros: int = field(default=0, init=False)
    _anchored: bool = field(default=False, init=False)
    _last_read: RedGoalObservation | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.plan.verifier_sha256 != red_forward_verifier_sha256(self.objective_id):
            raise ValueError("Red forward-goal verifier differs from its declaration")
        if (
            self.plan.goal_family != "red-story-objective"
            or not callable(self.observe)
            or not isinstance(
                self.meter,
                CompositionBudgetMeter,
            )
        ):
            raise ValueError("Red forward-goal collector contract differs")

        def append_without_actions(event: dict[str, object]) -> None:
            before = self.meter.checkpoint()
            known = event["kind"] != "forward_goal_observation" or event["goal"] is not None
            observation = self._last_read
            evidence = None
            if known:
                if observation is None:
                    raise ValueError("forward-goal evidence lacks a current observation")
                evidence = {
                    "mode": game_mode(observation.raw).value,
                    "current_facts": sorted(semantic_facts(observation.raw)),
                    "context": list(red_forward_context(observation)),
                    "consumables": {str(k): v for k, v in _consumable_stock(observation).items()},
                }
            self.append({**event, "red_evidence": evidence})
            if self.meter.checkpoint() != before:
                raise ValueError("forward-goal recording attempted game actions")

        self.recorder = ForwardGoalRecorder(self.plan, append_without_actions)

    @property
    def outcome(self) -> ForwardGoalOutcome | None:
        return self.recorder.outcome

    def _read(self) -> tuple[CompositionBudgetCheckpoint, RedGoalObservation]:
        before = self.meter.checkpoint()
        observation = self.observe()
        if not isinstance(observation, RedGoalObservation) or self.meter.checkpoint() != before:
            raise ValueError("forward-goal observation attempted actions or is invalid")
        self._last_read = observation
        return before, observation

    def _goal(self, observation: RedGoalObservation) -> bool:
        return red_forward_goal_observed(observation, self.objective_id)

    def prepare(self) -> None:
        if self._start is not None:
            raise ValueError("forward-goal collector was already prepared")
        before, initial = self._read()
        red_forward_context(initial)  # Fail absent/malformed PP before any actor input.
        stock = _consumable_stock(initial)
        self.recorder.declare(initial_goal=self._goal(initial))
        self._start, self._initial, self._stock = before, initial, stock

    def anchor(self, choice: ForwardGoalChoice) -> None:
        if self._start is None or self._initial is None or self._anchored:
            raise ValueError("forward-goal collector is not ready for its first choice")
        counter, current = self._read()
        if counter != self._start or current != self._initial:
            raise ValueError("forward-goal start changed before its first input")
        if (
            choice.context_names != RED_FORWARD_CONTEXT_NAMES
            or choice.context != red_forward_context(current)
        ):
            raise ValueError("forward-goal anchor does not contain the observed current resources")
        self.recorder.anchor(choice)
        self._anchored = True

    def after_macro(self, *, stop: bool = False) -> ForwardGoalOutcome | None:
        if not self._anchored or self._start is None or self.outcome is not None:
            raise ValueError("forward-goal collector has no active anchor")
        counter, observation = self._read()
        stock = _consumable_stock(observation)
        spent = self._spent + sum(
            max(0, count - stock[item]) for item, count in self._stock.items()
        )
        macros = self._macros + 1
        result = self.recorder.observe(
            ForwardGoalCounters(
                counter.controller_actions - self._start.controller_actions,
                counter.emulator_frames - self._start.emulator_frames,
                spent,
                macros,
            ),
            goal=self._goal(observation),
            stop=stop,
        )
        self._spent, self._macros, self._stock = spent, macros, stock
        return result

    def finish(self, *, interrupted: bool = False) -> ForwardGoalOutcome:
        if self.outcome is not None:
            return self.outcome  # A later report error never erases a durable goal.
        if not self._anchored or self._start is None:
            raise ValueError("forward-goal collector has no selected attempt")
        counter = self.meter.checkpoint()
        goal = None
        stock = self._stock
        spent = self._spent
        if not interrupted:
            counter, observation = self._read()
            goal = self._goal(observation)
            stock = _consumable_stock(observation)
            spent += sum(max(0, count - stock[item]) for item, count in self._stock.items())
        result = self.recorder.observe(
            ForwardGoalCounters(
                counter.controller_actions - self._start.controller_actions,
                counter.emulator_frames - self._start.emulator_frames,
                spent,
                self._macros,
            ),
            goal=goal,
            stop=True,
            interrupted=interrupted,
        )
        assert result is not None
        self._spent, self._stock = spent, stock
        return result
