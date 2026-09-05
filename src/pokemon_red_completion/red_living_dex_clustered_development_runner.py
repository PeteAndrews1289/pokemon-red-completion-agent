"""Development-only selection seam for frozen Red clustered schedules.

The historically qualified train consumer stays byte-for-byte immutable and
cannot parse the held suffix.  This sibling module authenticates only that
suffix and exposes no setup or controller API yet.  A separately versioned
development setup journal must consume this selection before real gameplay.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    validate_red_living_dex_clustered_private_plan,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    RedLivingDexClusteredTrainPlanBinding,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (
    RedLivingDexDevelopmentSupplementBinding,
    validate_red_living_dex_development_supplement,
)

RedLivingDexDevelopmentPlanBinding = (
    RedLivingDexClusteredTrainPlanBinding | RedLivingDexDevelopmentSupplementBinding
)

RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_SELECTION_SCHEMA = (
    "pokemon.red.living-dex-clustered-development-selection.v1"
)
RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_SELECTION_SHA256 = canonical_sha256(
    {
        "controller_api": False,
        "development_only": True,
        "model_fits": 0,
        "schema": RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_SELECTION_SCHEMA,
        "teacher_queries": 0,
        "train_ordinals_addressable": 0,
    }
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexClusteredDevelopmentRunnerError(RuntimeError):
    """A held Red selection cannot be authenticated."""


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredDevelopmentSelection:
    ordinal: int
    template_ordinal: int
    private_plan_sha256: str
    recipe_sha256: str
    slot_sha256: str
    logical_root_sha256: str = field(repr=False)
    physical_root_sha256: str = field(repr=False)
    root_state_sha256: str = field(repr=False)
    root_envelope_sha256: str = field(repr=False)
    context_identity_sha256: str = field(repr=False)
    upstream_lineage_sha256: str = field(repr=False)
    train_scenarios: int = field(repr=False)
    development_scenarios: int = field(repr=False)
    selection_contract_sha256: str = field(
        default=RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_SELECTION_SHA256,
        repr=False,
    )
    plan_kind: str = "clustered"

    def __post_init__(self) -> None:
        if (
            type(self.train_scenarios) is not int  # noqa: E721
            or self.plan_kind not in ("clustered", "supplement")
            or (self.plan_kind == "clustered" and self.train_scenarios <= 0)
            or (
                self.plan_kind == "supplement"
                and (self.train_scenarios != 0 or self.development_scenarios != 3)
            )
            or self.selection_contract_sha256
            != RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_SELECTION_SHA256
            or type(self.development_scenarios) is not int  # noqa: E721
            or self.development_scenarios <= 0
            or type(self.ordinal) is not int  # noqa: E721
            or not self.train_scenarios
            <= self.ordinal
            < self.train_scenarios + self.development_scenarios
            or type(self.template_ordinal) is not int  # noqa: E721
            or not 0 <= self.template_ordinal < 15
        ):
            raise RedLivingDexClusteredDevelopmentRunnerError(
                "train assignment is structurally inaccessible to development"
            )
        for value, subject in (
            (self.private_plan_sha256, "private plan"),
            (self.recipe_sha256, "recipe"),
            (self.slot_sha256, "slot"),
            (self.logical_root_sha256, "logical root"),
            (self.physical_root_sha256, "physical root"),
            (self.root_state_sha256, "root state"),
            (self.root_envelope_sha256, "root envelope"),
            (self.context_identity_sha256, "context"),
            (self.upstream_lineage_sha256, "lineage"),
            (self.selection_contract_sha256, "selection contract"),
        ):
            _digest(value, subject)

    def public_dict(self) -> dict[str, object]:
        return {
            "controller_api": False,
            "development_accessible": True,
            "model_predictions": 0,
            "ordinal_within_development": self.ordinal - self.train_scenarios,
            "partition": "development",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "setup_executions": 0,
            "template_ordinal": self.template_ordinal,
            "train_accessible": False,
        }


def authenticate_red_living_dex_clustered_development_selection(
    document: Mapping[str, object],
    ordinal: int,
    *,
    binding: RedLivingDexClusteredTrainPlanBinding,
) -> RedLivingDexClusteredDevelopmentSelection:
    """Strictly select one held suffix row from authenticated plan bytes."""

    if not isinstance(binding, RedLivingDexClusteredTrainPlanBinding):
        raise TypeError("development selection needs a plan binding")
    binding.__post_init__()
    if (
        type(ordinal) is not int  # noqa: E721
        or not binding.train_scenarios
        <= ordinal
        < binding.train_scenarios + binding.development_scenarios
    ):
        raise RedLivingDexClusteredDevelopmentRunnerError(
            "train assignment is structurally inaccessible to development"
        )
    try:
        schedule = validate_red_living_dex_clustered_private_plan(
            document,
            expected_schedule_sha256=binding.schedule_sha256,
            expected_policy_sha256=binding.policy_sha256,
        )
        assignments = document.get("assignments")
        if (
            document.get("private_plan_sha256") != binding.private_plan_sha256
            or schedule.policy.train_scenarios != binding.train_scenarios
            or schedule.policy.development_scenarios != binding.development_scenarios
            or not isinstance(assignments, list)
            or len(assignments) != binding.train_scenarios + binding.development_scenarios
        ):
            raise ValueError("development plan differs")
        selected = assignments[ordinal]
        if (
            not isinstance(selected, Mapping)
            or selected.get("ordinal") != ordinal
            or selected.get("partition") != "development"
        ):
            raise ValueError("development assignment differs")
        return RedLivingDexClusteredDevelopmentSelection(
            ordinal=ordinal,
            template_ordinal=_integer(selected.get("template_ordinal"), "template"),
            private_plan_sha256=binding.private_plan_sha256,
            recipe_sha256=_digest(selected.get("recipe_sha256"), "recipe"),
            slot_sha256=_digest(selected.get("template_sha256"), "slot"),
            logical_root_sha256=_digest(
                selected.get("root_consumption_sha256"),
                "logical root",
            ),
            physical_root_sha256=_digest(
                selected.get("physical_root_sha256"),
                "physical root",
            ),
            root_state_sha256=_digest(selected.get("root_state_sha256"), "state"),
            root_envelope_sha256=_digest(
                selected.get("root_envelope_sha256"),
                "envelope",
            ),
            context_identity_sha256=_digest(
                selected.get("context_identity_sha256"),
                "context",
            ),
            upstream_lineage_sha256=_digest(
                selected.get("lineage_sha256"),
                "lineage",
            ),
            train_scenarios=binding.train_scenarios,
            development_scenarios=binding.development_scenarios,
        )
    except RedLivingDexClusteredDevelopmentRunnerError:
        raise
    except (TypeError, ValueError):
        raise RedLivingDexClusteredDevelopmentRunnerError(
            "clustered development plan authentication failed"
        ) from None


def authenticate_red_living_dex_development_selection(
    document: Mapping[str, object],
    ordinal: int,
    *,
    binding: RedLivingDexDevelopmentPlanBinding,
) -> RedLivingDexClusteredDevelopmentSelection:
    """Dispatch explicit plan types; the historical train parser remains unchanged."""

    if isinstance(binding, RedLivingDexClusteredTrainPlanBinding):
        return authenticate_red_living_dex_clustered_development_selection(
            document, ordinal, binding=binding
        )
    if not isinstance(binding, RedLivingDexDevelopmentSupplementBinding):
        raise TypeError("development selection needs an explicit plan binding")
    try:
        validate_red_living_dex_development_supplement(document, binding=binding)
        if type(ordinal) is not int or not 0 <= ordinal < 3:  # noqa: E721
            raise ValueError("supplement ordinal")
        assignments = document["assignments"]
        assert isinstance(assignments, list)
        selected = assignments[ordinal]
        return RedLivingDexClusteredDevelopmentSelection(
            ordinal=ordinal,
            template_ordinal=_integer(selected["template_ordinal"], "template"),
            private_plan_sha256=binding.private_plan_sha256,
            recipe_sha256=selected["recipe_sha256"],
            slot_sha256=selected["template_sha256"],
            logical_root_sha256=selected["root_consumption_sha256"],
            physical_root_sha256=selected["physical_root_sha256"],
            root_state_sha256=selected["root_state_sha256"],
            root_envelope_sha256=selected["root_envelope_sha256"],
            context_identity_sha256=selected["context_identity_sha256"],
            upstream_lineage_sha256=selected["lineage_sha256"],
            train_scenarios=0,
            development_scenarios=3,
            plan_kind="supplement",
        )
    except (KeyError, TypeError, ValueError):
        raise RedLivingDexClusteredDevelopmentRunnerError(
            "supplement development plan authentication failed"
        ) from None


def load_red_living_dex_development_selection(
    store: PrivateArtifactRoot,
    ordinal: int,
    *,
    binding: RedLivingDexDevelopmentPlanBinding,
) -> tuple[RedLivingDexClusteredDevelopmentSelection, Mapping[str, object]]:
    """Reopen the exact immutable private record before interpreting any row."""

    selection, _record, document = reopen_red_living_dex_development_selection(
        store,
        ordinal,
        binding=binding,
    )
    return selection, document


def reopen_red_living_dex_development_selection(
    store: PrivateArtifactRoot,
    ordinal: int,
    *,
    binding: RedLivingDexDevelopmentPlanBinding,
) -> tuple[
    RedLivingDexClusteredDevelopmentSelection,
    PrivateSealedRecord,
    Mapping[str, object],
]:
    """Reopen the record and retain its object identity for recovery checks."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("development selection needs its private store")
    if not isinstance(
        binding, (RedLivingDexClusteredTrainPlanBinding, RedLivingDexDevelopmentSupplementBinding)
    ):
        raise TypeError("development selection needs an explicit plan binding")
    binding.__post_init__()
    record = store.find_sealed_record(binding.record_id, expected_kind=binding.record_kind)
    if (
        record is None
        or record.summary.manifest_sha256 != binding.plan_manifest_sha256
        or record.summary.record_sha256 != binding.plan_record_sha256
    ):
        raise RedLivingDexClusteredDevelopmentRunnerError("development plan record differs")
    document = record.read()
    return (
        authenticate_red_living_dex_development_selection(document, ordinal, binding=binding),
        record,
        document,
    )


def _digest(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexClusteredDevelopmentRunnerError(
            f"clustered development {subject} differs"
        )
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexClusteredDevelopmentRunnerError(
            f"clustered development {subject} differs"
        )
    return value


__all__ = [
    "RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_SELECTION_SCHEMA",
    "RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_SELECTION_SHA256",
    "RedLivingDexClusteredDevelopmentRunnerError",
    "RedLivingDexClusteredDevelopmentSelection",
    "authenticate_red_living_dex_clustered_development_selection",
    "authenticate_red_living_dex_development_selection",
    "load_red_living_dex_development_selection",
    "RedLivingDexDevelopmentPlanBinding",
    "reopen_red_living_dex_development_selection",
]
