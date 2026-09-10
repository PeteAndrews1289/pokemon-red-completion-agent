"""Path-free costs of deterministic storage support, not a learned decision."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoragePreparationSummary:
    box_rotations: int
    collection_preserved: bool
    setup_training_rows: int
    actions_executed: int | None = None
    frames_executed: int | None = None
    initial_headroom: int | None = None
    prepared_headroom: int | None = None

    def __post_init__(self) -> None:
        if (
            type(self.box_rotations) is not int
            or self.box_rotations != 1
            or self.collection_preserved is not True
            or type(self.setup_training_rows) is not int
            or self.setup_training_rows != 0
        ):
            raise ValueError("storage preparation invariant differs")
        for name, maximum in (
            ("actions_executed", 10_000_000),
            ("frames_executed", 1_000_000_000),
            ("initial_headroom", 26),
            ("prepared_headroom", 26),
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or not 0 <= value <= maximum):
                raise ValueError("storage preparation diagnostic bounds differ")
        for first, second in (
            (self.actions_executed, self.frames_executed),
            (self.initial_headroom, self.prepared_headroom),
        ):
            if (first is None) != (second is None):
                raise ValueError("storage preparation diagnostic pair differs")

    def public_dict(self) -> dict[str, object]:
        return {
            name: value
            for name in self.__dataclass_fields__
            if (value := getattr(self, name)) is not None
        }

    @classmethod
    def from_evidence(cls, evidence: Mapping[str, object]) -> StoragePreparationSummary | None:
        value = evidence.get("storage_preparation")
        if value is None:
            return None
        required = {"box_rotations", "collection_preserved", "setup_training_rows"}
        if not isinstance(value, Mapping) or not required <= set(value) <= set(
            cls.__dataclass_fields__
        ):
            raise ValueError("storage preparation diagnostic fields differ")
        # Preserve older summaries without inventing previously unrecorded costs.
        return cls(**dict(value))
