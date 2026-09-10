"""Public-safe diagnostics for bounded encounter-source capture surveys.

This module provides path-free, species-free summary statistics for capture
survey execution reports. It records counts of actions, encounters, captures,
and flees, as well as terminal stop states. It is strictly diagnostic and never
participates in policy decisions, learner features, or targets.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

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
_ALLOWED_EVIDENCE_FIELDS = _REQUIRED_EVIDENCE_FIELDS | {"search_stop_reason"}


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
        for name in ("search_exhausted", "safety_stopped"):
            value = getattr(self, name)
            if type(value) is not bool:
                raise ValueError(f"{name} must be an exact bool")
        if self.captures + self.flees > self.encounters_seen:
            raise ValueError("captures and flees cannot exceed encounters seen")
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
        )
