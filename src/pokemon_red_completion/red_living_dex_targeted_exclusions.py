"""Authenticate prior Red lineages solely to exclude them from a new capacity gate."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pokemon_red_completion.living_dex_development_supplement import (
    LivingDexDevelopmentSupplementPlan,
)
from pokemon_red_completion.red_living_dex_development_supply import (
    RedLivingDexDevelopmentSupplyInventory,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexTargetedExclusionError(ValueError):
    """Prior train and development identities cannot form a safe exclusion set."""


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedExclusionInventory:
    """Private identity sets with only aggregate public serialization."""

    train_lineages: frozenset[str]
    development_lineages: frozenset[str]
    development_physical_roots: frozenset[str]
    historical_development_roots: int
    supplemental_development_roots: int

    def __post_init__(self) -> None:
        for values, subject in (
            (self.train_lineages, "train lineages"),
            (self.development_lineages, "development lineages"),
            (self.development_physical_roots, "development physical roots"),
        ):
            if (
                not isinstance(values, frozenset)
                or not values
                or any(
                    not isinstance(value, str) or _SHA256.fullmatch(value) is None
                    for value in values
                )
            ):
                raise RedLivingDexTargetedExclusionError(
                    f"targeted exclusion {subject} differ"
                )
        for value in (
            self.historical_development_roots,
            self.supplemental_development_roots,
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise RedLivingDexTargetedExclusionError(
                    "targeted exclusion development denominator differs"
                )
        if (
            self.train_lineages & self.development_lineages
            or len(self.development_lineages)
            != self.historical_development_roots
            + self.supplemental_development_roots
            or len(self.development_physical_roots) != len(self.development_lineages)
        ):
            raise RedLivingDexTargetedExclusionError(
                "targeted exclusion identity families overlap"
            )

    @property
    def excluded_lineages(self) -> frozenset[str]:
        return self.train_lineages | self.development_lineages

    def public_dict(self) -> dict[str, object]:
        return {
            "controller_actions": 0,
            "development_lineages_excluded": len(self.development_lineages),
            "development_physical_roots_excluded": len(
                self.development_physical_roots
            ),
            "historical_development_roots": self.historical_development_roots,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_opened": 0,
            "private_identity_fields": 0,
            "root_claims": 0,
            "supplemental_development_roots": self.supplemental_development_roots,
            "teacher_queries": 0,
            "train_lineages_excluded": len(self.train_lineages),
        }


def build_red_living_dex_targeted_exclusions(
    supply: RedLivingDexDevelopmentSupplyInventory,
    supplement: LivingDexDevelopmentSupplementPlan,
) -> RedLivingDexTargetedExclusionInventory:
    """Join prior train and development plans without reading their outcomes."""

    if not isinstance(supply, RedLivingDexDevelopmentSupplyInventory):
        raise TypeError("targeted exclusions need the authenticated Red supply")
    if not isinstance(supplement, LivingDexDevelopmentSupplementPlan):
        raise TypeError("targeted exclusions need the authenticated supplement")
    supply.__post_init__()
    supplement.__post_init__()
    historical_lineages = frozenset(
        root.lineage_sha256 for root in supply.historical_roots
    )
    supplemental_lineages = frozenset(
        assignment.lineage_sha256 for assignment in supplement.assignments
    )
    historical_physical = frozenset(
        root.physical_root_sha256 for root in supply.historical_roots
    )
    supplemental_physical = frozenset(
        assignment.physical_root_sha256 for assignment in supplement.assignments
    )
    if (
        historical_lineages & supplemental_lineages
        or historical_physical & supplemental_physical
    ):
        raise RedLivingDexTargetedExclusionError(
            "targeted supplement repeats a historical development root"
        )
    return RedLivingDexTargetedExclusionInventory(
        train_lineages=supply.train_lineages,
        development_lineages=historical_lineages | supplemental_lineages,
        development_physical_roots=historical_physical | supplemental_physical,
        historical_development_roots=len(supply.historical_roots),
        supplemental_development_roots=len(supplement.assignments),
    )


__all__ = [
    "RedLivingDexTargetedExclusionError",
    "RedLivingDexTargetedExclusionInventory",
    "build_red_living_dex_targeted_exclusions",
]
