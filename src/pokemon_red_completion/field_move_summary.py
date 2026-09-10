"""Path-free counts of completed field macros, never policy features or fit targets."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FieldMoveSummary:
    cuts: int = 0
    surfs: int = 0
    flights: int = 0

    def __post_init__(self) -> None:
        if any(type(v) is not int or not 0 <= v <= 10_000
               for v in (self.cuts, self.surfs, self.flights)):
            raise ValueError("field move summary counts differ")

    def public_dict(self) -> dict[str, int]:
        return {"cuts": self.cuts, "surfs": self.surfs, "flights": self.flights}

    def plus(self, other: FieldMoveSummary) -> FieldMoveSummary:
        return FieldMoveSummary(self.cuts + other.cuts, self.surfs + other.surfs,
                                self.flights + other.flights)

    @classmethod
    def from_evidence(cls, evidence: Mapping[str, object]) -> FieldMoveSummary | None:
        value = evidence.get("field_moves")
        if value is None:
            return None
        if not isinstance(value, Mapping) or set(value) != {"cuts", "surfs", "flights"}:
            raise ValueError("field move summary fields differ")
        return cls(value["cuts"], value["surfs"], value["flights"])
