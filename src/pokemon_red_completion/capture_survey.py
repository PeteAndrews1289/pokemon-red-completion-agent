"""Public-safe diagnostics for bounded encounter-source capture surveys.

This module provides path-free, species-free summary statistics for capture
survey execution reports. It records counts of actions, encounters, captures,
and flees, as well as terminal stop states. It is strictly diagnostic and never
participates in policy decisions, learner features, or targets.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic

MAX_SEMANTIC_ACTIONS = 10_000_000
MAX_SURVEY_COUNT = 1_000_000
ALLOWED_SEARCH_STOP_REASON = "survey_leg_limit_exceeded"
_REQUIRED_EVIDENCE_FIELDS = frozenset({
    "semantic_actions",
    "encounters_seen",
    "captures",
    "flees",
    "search_exhausted",
    "safety_stopped",
})
_ALLOWED_EVIDENCE_FIELDS = _REQUIRED_EVIDENCE_FIELDS | {
    "search_stop_reason", "capture_items_exhausted",
}


def capture_diagnostic_observation(raw, *, ball=None, ball_quantity=None):
    """Private decoded capture facts; stale enemy fields are not live targets."""
    live = getattr(raw, "battle_state", None) == 1
    fields = {
        "target_species_id": "enemy_species_id", "target_level": "enemy_level",
        "target_hp": "enemy_hp", "target_max_hp": "enemy_max_hp", "target_status": "enemy_status",
    }
    facts = {name: getattr(raw, source, None) if live else None for name, source in fields.items()}
    facts.update(
        map_id=getattr(raw, "map_id", None),
        player_x=getattr(raw, "player_x", None), player_y=getattr(raw, "player_y", None),
        target_fields_live=live,
        catcher_hp=getattr(raw, "battler_hp", None),
        catcher_status=getattr(raw, "battler_status", None),
        catcher_pp=getattr(raw, "battler_pp", None),
        battle_state=getattr(raw, "battle_state", None),
        ball_id=None if ball is None else int(ball), ball_quantity=ball_quantity,
        critical_hit_observed=None, miss_observed=None,
    )
    hp, maximum = facts["target_hp"], facts["target_max_hp"]
    facts["target_hp_fraction"] = (
        hp / maximum if type(hp) is int and type(maximum) is int and maximum > 0 else None
    )
    facts["unknown_fields"] = [k for k, v in facts.items() if v is None]
    return facts


def capture_execution_counters(emulator, executor):
    """No input: native counters and a monotonic stamp for one throw."""
    return dict(
        actions=getattr(executor, "actions_executed", None),
        frames=getattr(emulator, "frame_count", None), seconds=monotonic(),
    )


def record_capture_diagnostic(executor, kind, raw, *, source, throw, ball,
                              ball_quantity, outcome=None, before_counters=None,
                              counters=None):
    """Use the existing input journal, not a second logging or control path."""
    record = getattr(executor, "record_diagnostic_event", None)
    if not callable(record):
        return
    costs = None
    if before_counters is not None and counters is not None:
        costs = {
            key: b - a if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
            for key in ("actions", "frames", "seconds")
            for a, b in [(before_counters.get(key), counters.get(key))]
        }
    record(kind, dict(
        schema="pokemon.red.capture-throw-diagnostics.v1", diagnostic_only=True,
        selection_authority="deterministic_capture_support", source=source,
        throw=throw, outcome=outcome, measured_cost=costs,
        conditions=capture_diagnostic_observation(raw, ball=ball, ball_quantity=ball_quantity),
        training_admission=False,
    ))


def survey_operation_diagnostics(before, after, *, operation, elapsed_seconds):
    """An observed operation is not automatically an eligible encounter step."""
    old, new = before or {}, after or {}
    measured = {}
    for name in ("native_actions", "native_frames"):
        a, b = old.get(name), new.get(name)
        measured[name] = b - a if type(a) is int and type(b) is int else None
    old_search, new_search = old.get("search_exposure") or {}, new.get("search_exposure") or {}
    for name in ("movement_steps", "eligible_search_steps", "search_requests"):
        a, b = old_search.get(name), new_search.get(name)
        measured[name] = b - a if type(a) is int and type(b) is int else None
    return dict(
        schema="pokemon.red.survey-operation-diagnostics.v1", diagnostic_only=True,
        operation=operation, elapsed_seconds=elapsed_seconds, measured=measured,
        context_before={
            k: old.get(k) for k in ("map_id", "player_x", "player_y", "repel_remaining_steps",
                                   "party_levels", "movement_mode", "physical_search_context_sha256")
        },
        target_after=capture_diagnostic_observation_from_state(new),
        search_eligibility_known=measured["eligible_search_steps"] is not None,
        search_likelihood_not_inferred=True,
    )


def capture_diagnostic_observation_from_state(state):
    """A survey's existing decoded state, without a new native read."""
    live = state.get("battle_state") == 1
    return dict(
        target_fields_live=live,
        **{k: state.get(k) if live else None for k in
           ("enemy_species_id", "enemy_level", "enemy_hp", "enemy_max_hp", "enemy_status")},
    )


@dataclass(frozen=True, slots=True)
class CaptureSurveySummary:
    """Public-safe observed survey diagnostics; never a policy feature or target."""

    semantic_actions: int
    encounters_seen: int
    captures: int
    flees: int
    search_exhausted: bool
    safety_stopped: bool
    search_stop_reason: str | None = None
    capture_items_exhausted: bool = False

    def __post_init__(self) -> None:
        for name, maximum in (
            ("semantic_actions", MAX_SEMANTIC_ACTIONS),
            ("encounters_seen", MAX_SURVEY_COUNT),
            ("captures", MAX_SURVEY_COUNT),
            ("flees", MAX_SURVEY_COUNT),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError(
                    f"{name} must be an exact non-negative bounded integer <= {maximum}"
                )
        for name in ("search_exhausted", "safety_stopped", "capture_items_exhausted"):
            value = getattr(self, name)
            if type(value) is not bool:
                raise ValueError(f"{name} must be an exact bool")
        if self.captures + self.flees > self.encounters_seen:
            raise ValueError("captures and flees cannot exceed encounters seen")
        if self.capture_items_exhausted and (self.search_exhausted or self.safety_stopped):
            raise ValueError("capture item exhaustion must be a distinct terminal stop")
        if (
            self.search_stop_reason is not None
            and self.search_stop_reason != ALLOWED_SEARCH_STOP_REASON
        ):
            raise ValueError(
                f"search_stop_reason if present must be {ALLOWED_SEARCH_STOP_REASON!r}"
            )
        if self.search_stop_reason is not None and (
            not self.search_exhausted or self.safety_stopped
        ):
            raise ValueError(
                "search_stop_reason requires search_exhausted=True and safety_stopped=False"
            )

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "semantic_actions": self.semantic_actions,
            "encounters_seen": self.encounters_seen,
            "captures": self.captures,
            "flees": self.flees,
            "search_exhausted": self.search_exhausted,
            "safety_stopped": self.safety_stopped,
        }
        if self.search_stop_reason is not None:
            result["search_stop_reason"] = self.search_stop_reason
        if self.capture_items_exhausted:
            result["capture_items_exhausted"] = True
        return result

    @classmethod
    def from_evidence(
        cls, evidence: Mapping[str, object]
    ) -> CaptureSurveySummary | None:
        if not isinstance(evidence, Mapping):
            raise TypeError("evidence must be a mapping")
        if "capture_survey" not in evidence:
            return None
        raw = evidence["capture_survey"]
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise ValueError("capture_survey must be a mapping")

        raw_keys = set(raw.keys())
        if not (_REQUIRED_EVIDENCE_FIELDS <= raw_keys <= _ALLOWED_EVIDENCE_FIELDS):
            raise ValueError("capture_survey fields differ from required contract")

        stop_reason: str | None = None
        if "search_stop_reason" in raw:
            raw_reason = raw["search_stop_reason"]
            if not isinstance(raw_reason, str) or raw_reason != ALLOWED_SEARCH_STOP_REASON:
                raise ValueError(
                    f"search_stop_reason if present must be {ALLOWED_SEARCH_STOP_REASON!r}"
                )
            stop_reason = raw_reason

        return cls(
            semantic_actions=raw["semantic_actions"],  # type: ignore[arg-type]
            encounters_seen=raw["encounters_seen"],  # type: ignore[arg-type]
            captures=raw["captures"],  # type: ignore[arg-type]
            flees=raw["flees"],  # type: ignore[arg-type]
            search_exhausted=raw["search_exhausted"],  # type: ignore[arg-type]
            safety_stopped=raw["safety_stopped"],  # type: ignore[arg-type]
            search_stop_reason=stop_reason,
            capture_items_exhausted=raw.get("capture_items_exhausted", False),  # type: ignore[arg-type]
        )
