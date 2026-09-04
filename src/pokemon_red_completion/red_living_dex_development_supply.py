"""Action-free audit of frozen Red causal-development supply.

The complete causal corpus can now fit a title-neutral option-value model, but
model authority still needs genuinely unseen Red outcomes.  Two historical
clustered schedules reserved development assignments before any train outcome
was collected.  This module authenticates those exact schedules, deduplicates
their roots, checks the account-wide claim ledger, proves separation from the
complete train corpus, and binds the exact shadow model without opening a ROM or
one development outcome.

The result is intentionally aggregate-only.  Lineages, roots, state hashes,
dataset identity, private paths, and individual availability never cross the
public boundary.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.claim_first_admission import (
    claim_first_availability_snapshot_lease,
)
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
)
from pokemon_red_completion.living_dex_causal_journal import (
    load_living_dex_authenticated_causal_examples,
)
from pokemon_red_completion.living_dex_clustered_curriculum import (
    LivingDexClusteredScenarioCapability,
)
from pokemon_red_completion.living_dex_development_supplement import (
    LivingDexDevelopmentSupplementCapability,
)
from pokemon_red_completion.living_dex_goal_model_record import (
    load_living_dex_goal_model_record_bytes,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OBJECTIVE,
    living_dex_option_train_dataset_sha256,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
)
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    validate_red_living_dex_clustered_private_plan,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    FROZEN_RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_PLAN,
    FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN,
    RedLivingDexClusteredTrainPlanBinding,
)

RED_LIVING_DEX_DEVELOPMENT_SUPPLY_RESULT_SCHEMA = (
    "pokemon.red.living-dex-development-supply-audit.v1"
)
MINIMUM_DEVELOPMENT_ROOTS = 4
DEVELOPMENT_SETUP_CENSOR_ALLOWANCE = 1

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ASSIGNMENT_FIELDS = {
    "available_option_kinds",
    "context_identity_sha256",
    "lineage_sha256",
    "ordinal",
    "partition",
    "physical_root_sha256",
    "recipe",
    "recipe_sha256",
    "root_consumption_sha256",
    "root_envelope_sha256",
    "root_state_sha256",
    "scenario_sha256",
    "template_ordinal",
    "template_sha256",
    "within_lineage_ordinal",
}


class RedLivingDexDevelopmentSupplyError(RuntimeError):
    """The private supply, train corpus, claim ledger, or model failed closed."""


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentRoot:
    """Private root identity used only while computing aggregate readiness."""

    lineage_sha256: str
    logical_root_sha256: str
    physical_root_sha256: str
    state_sha256: str
    envelope_sha256: str
    option_kinds: frozenset[str]

    def __post_init__(self) -> None:
        for value in (
            self.lineage_sha256,
            self.logical_root_sha256,
            self.physical_root_sha256,
            self.state_sha256,
            self.envelope_sha256,
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise RedLivingDexDevelopmentSupplyError("development root identity differs")
        if (
            self.logical_root_sha256 == self.physical_root_sha256
            or not isinstance(self.option_kinds, frozenset)
            or not self.option_kinds
            or any(not isinstance(item, str) or not item for item in self.option_kinds)
        ):
            raise RedLivingDexDevelopmentSupplyError("development root semantics differ")

    @property
    def deduplication_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.lineage_sha256,
            self.logical_root_sha256,
            self.physical_root_sha256,
            self.state_sha256,
            self.envelope_sha256,
        )


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplyResult:
    """Path-free answer to whether held Red development can run now."""

    authenticated_train_examples: int
    model_sha256: str
    model_record_sha256: str
    model_settled_examples: int
    schedules_authenticated: int
    scheduled_development_assignments: int
    unique_development_roots: int
    duplicate_schedule_assignments: int
    available_development_roots: int
    unavailable_development_roots: int
    available_development_lineages: int
    available_option_kinds: tuple[str, ...]
    lineage_overlap_with_train: int
    state_overlap_with_train: int
    required_development_roots: int = MINIMUM_DEVELOPMENT_ROOTS
    setup_censor_allowance: int = DEVELOPMENT_SETUP_CENSOR_ALLOWANCE

    def __post_init__(self) -> None:
        counts = (
            self.authenticated_train_examples,
            self.model_settled_examples,
            self.schedules_authenticated,
            self.scheduled_development_assignments,
            self.unique_development_roots,
            self.duplicate_schedule_assignments,
            self.available_development_roots,
            self.unavailable_development_roots,
            self.available_development_lineages,
            self.lineage_overlap_with_train,
            self.state_overlap_with_train,
            self.required_development_roots,
            self.setup_censor_allowance,
        )
        if (
            any(type(value) is not int or value < 0 for value in counts)  # noqa: E721
            or self.authenticated_train_examples == 0
            or self.model_settled_examples != self.authenticated_train_examples
            or self.schedules_authenticated == 0
            or self.scheduled_development_assignments
            != self.unique_development_roots + self.duplicate_schedule_assignments
            or self.unique_development_roots
            != self.available_development_roots + self.unavailable_development_roots
            or self.available_development_lineages > self.available_development_roots
            or not isinstance(self.available_option_kinds, tuple)
            or tuple(sorted(set(self.available_option_kinds))) != self.available_option_kinds
            or not isinstance(self.model_sha256, str)
            or _SHA256.fullmatch(self.model_sha256) is None
            or not isinstance(self.model_record_sha256, str)
            or _SHA256.fullmatch(self.model_record_sha256) is None
        ):
            raise RedLivingDexDevelopmentSupplyError("development supply diagnostics differ")

    @property
    def supply_ready(self) -> bool:
        return (
            self.lineage_overlap_with_train == 0
            and self.state_overlap_with_train == 0
            and self.available_development_roots >= self.required_development_roots
            and self.available_development_lineages >= self.required_development_roots
        )

    @property
    def development_root_shortfall(self) -> int:
        return max(0, self.required_development_roots - self.available_development_roots)

    @property
    def minimum_new_roots_to_freeze(self) -> int:
        if self.development_root_shortfall == 0:
            return 0
        return self.development_root_shortfall + self.setup_censor_allowance

    @property
    def missing_option_kinds(self) -> tuple[str, ...]:
        available = set(self.available_option_kinds)
        return tuple(
            sorted(
                item.value for item in RED_DIRECT_CAUSAL_OPTION_KINDS if item.value not in available
            )
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "authority": "non_authoritative_shadow_only",
            "available_development_lineages": self.available_development_lineages,
            "available_development_roots": self.available_development_roots,
            "available_option_kinds": list(self.available_option_kinds),
            "controller_actions": 0,
            "crystal_accesses": 0,
            "development_examples_read": 0,
            "development_outcomes_opened": 0,
            "development_root_shortfall": self.development_root_shortfall,
            "duplicate_schedule_assignments": self.duplicate_schedule_assignments,
            "emulator_frames": 0,
            "lineage_overlap_with_train": self.lineage_overlap_with_train,
            "minimum_new_roots_to_freeze": self.minimum_new_roots_to_freeze,
            "missing_option_kinds": list(self.missing_option_kinds),
            "model": {
                "model_sha256": self.model_sha256,
                "record_sha256": self.model_record_sha256,
                "settled_examples": self.model_settled_examples,
            },
            "model_fits": 0,
            "model_predictions": 0,
            "objective": LIVING_DEX_OPTION_OBJECTIVE,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "required_development_roots": self.required_development_roots,
            "scheduled_development_assignments": (self.scheduled_development_assignments),
            "schedules_authenticated": self.schedules_authenticated,
            "schema": RED_LIVING_DEX_DEVELOPMENT_SUPPLY_RESULT_SCHEMA,
            "setup_censor_allowance": self.setup_censor_allowance,
            "state_overlap_with_train": self.state_overlap_with_train,
            "status": (
                "development_supply_ready" if self.supply_ready else "development_supply_shortfall"
            ),
            "teacher_queries": 0,
            "train_examples_authenticated": self.authenticated_train_examples,
            "transfer_claimed": False,
            "unavailable_development_roots": self.unavailable_development_roots,
            "unique_development_roots": self.unique_development_roots,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplyInventory:
    """Private exclusion inventory retained only by an action-free freezer."""

    result: RedLivingDexDevelopmentSupplyResult
    train_lineages: frozenset[str]
    train_states: frozenset[tuple[str, str]]
    historical_roots: tuple[RedLivingDexDevelopmentRoot, ...]
    available_roots: tuple[RedLivingDexDevelopmentRoot, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.result, RedLivingDexDevelopmentSupplyResult):
            raise TypeError("development supply inventory needs its public result")
        self.result.__post_init__()
        if (
            not isinstance(self.train_lineages, frozenset)
            or not self.train_lineages
            or any(
                not isinstance(item, str) or _SHA256.fullmatch(item) is None
                for item in self.train_lineages
            )
            or not isinstance(self.train_states, frozenset)
            or not self.train_states
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or any(
                    not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in item
                )
                for item in self.train_states
            )
            or not isinstance(self.historical_roots, tuple)
            or not isinstance(self.available_roots, tuple)
            or any(
                not isinstance(item, RedLivingDexDevelopmentRoot)
                for item in (*self.historical_roots, *self.available_roots)
            )
        ):
            raise RedLivingDexDevelopmentSupplyError("development supply private inventory differs")
        for root in (*self.historical_roots, *self.available_roots):
            root.__post_init__()
        historical = {item.deduplication_key for item in self.historical_roots}
        available = {item.deduplication_key for item in self.available_roots}
        if (
            len(historical) != len(self.historical_roots)
            or len(available) != len(self.available_roots)
            or not available.issubset(historical)
            or len(self.historical_roots) != self.result.unique_development_roots
            or len(self.available_roots) != self.result.available_development_roots
            or len(self.train_lineages) > self.result.authenticated_train_examples
            or len(self.train_states) > self.result.authenticated_train_examples
        ):
            raise RedLivingDexDevelopmentSupplyError(
                "development supply private inventory does not match its result"
            )


def audit_red_living_dex_development_supply(
    store: PrivateArtifactRoot,
    *,
    claim_registry: Path,
    expected_model_sha256: str,
    expected_model_record_sha256: str,
    bindings: Sequence[RedLivingDexClusteredTrainPlanBinding] = (
        FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN,
        FROZEN_RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_PLAN,
    ),
) -> RedLivingDexDevelopmentSupplyResult:
    """Authenticate held roots and the exact train-only model without effects."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("development supply audit needs a private artifact root")
    if not isinstance(claim_registry, Path):
        raise TypeError("development supply audit needs a claim registry Path")
    if (
        not isinstance(expected_model_sha256, str)
        or _SHA256.fullmatch(expected_model_sha256) is None
        or not isinstance(expected_model_record_sha256, str)
        or _SHA256.fullmatch(expected_model_record_sha256) is None
    ):
        raise RedLivingDexDevelopmentSupplyError("expected model identity differs")
    if isinstance(bindings, (str, bytes)) or not isinstance(bindings, Sequence):
        raise TypeError("development supply bindings need a sequence")

    try:
        authenticated = load_living_dex_authenticated_causal_examples(store)
        if not authenticated or any(item.identity.partition != "train" for item in authenticated):
            raise RedLivingDexDevelopmentSupplyError("causal corpus is not train-only")
        rows = tuple(item.example for item in authenticated)
        dataset_sha256 = living_dex_option_train_dataset_sha256(rows)
        model_record = store.find_sealed_record(
            f"lc-update-model-{dataset_sha256}",
            expected_kind="living_dex_causal_integration_model",
        )
        if (
            model_record is None
            or model_record.summary.record_sha256 != expected_model_record_sha256
        ):
            raise RedLivingDexDevelopmentSupplyError("causal model record differs")
        model = load_living_dex_goal_model_record_bytes(
            model_record.read_bytes(),
            expected_model_sha256=expected_model_sha256,
        )
        if (
            model.file_sha256 != expected_model_record_sha256
            or model.model.train_dataset_sha256 != dataset_sha256
            or model.model.settled_examples != len(authenticated)
        ):
            raise RedLivingDexDevelopmentSupplyError("causal model corpus join differs")

        plan_roots: list[RedLivingDexDevelopmentRoot] = []
        for binding in bindings:
            plan_roots.extend(_load_plan_development_roots(store, binding))
        train_lineages = {item.identity.lineage_sha256 for item in authenticated}
        train_states = {
            (item.identity.state_sha256, item.identity.envelope_sha256) for item in authenticated
        }
        unique_roots = _deduplicate_roots(plan_roots)
        root_pairs = tuple(
            (root.logical_root_sha256, root.physical_root_sha256) for root in unique_roots
        )
        with claim_first_availability_snapshot_lease(claim_registry) as lease:
            availability = lease.observe(root_pairs)
        available_pairs = {
            (item.logical_root_sha256, item.physical_root_sha256)
            for item in availability.observations
            if item.available
        }
        available = tuple(
            root
            for root in unique_roots
            if (root.logical_root_sha256, root.physical_root_sha256) in available_pairs
        )
        return RedLivingDexDevelopmentSupplyResult(
            authenticated_train_examples=len(authenticated),
            model_sha256=model.model.model_sha256,
            model_record_sha256=model.file_sha256,
            model_settled_examples=model.model.settled_examples,
            schedules_authenticated=len(bindings),
            scheduled_development_assignments=len(plan_roots),
            unique_development_roots=len(unique_roots),
            duplicate_schedule_assignments=len(plan_roots) - len(unique_roots),
            available_development_roots=len(available),
            unavailable_development_roots=len(unique_roots) - len(available),
            available_development_lineages=len({root.lineage_sha256 for root in available}),
            available_option_kinds=tuple(
                sorted({kind for root in available for kind in root.option_kinds})
            ),
            lineage_overlap_with_train=sum(
                root.lineage_sha256 in train_lineages for root in unique_roots
            ),
            state_overlap_with_train=sum(
                (root.state_sha256, root.envelope_sha256) in train_states for root in unique_roots
            ),
        )
    except RedLivingDexDevelopmentSupplyError:
        raise
    except BaseException:
        raise RedLivingDexDevelopmentSupplyError(
            "development supply authentication failed"
        ) from None


def inventory_red_living_dex_development_supply(
    store: PrivateArtifactRoot,
    *,
    claim_registry: Path,
    expected_model_sha256: str,
    expected_model_record_sha256: str,
    bindings: Sequence[RedLivingDexClusteredTrainPlanBinding] = (
        FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN,
        FROZEN_RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_PLAN,
    ),
) -> RedLivingDexDevelopmentSupplyInventory:
    """Reopen the authenticated supply only to derive private exclusions.

    The public audit remains the authority for counts and model identity.  This
    second pass exposes no public serializer and verifies that its private root
    sets reproduce every relevant public count before a freezer may use them.
    """

    result = audit_red_living_dex_development_supply(
        store,
        claim_registry=claim_registry,
        expected_model_sha256=expected_model_sha256,
        expected_model_record_sha256=expected_model_record_sha256,
        bindings=bindings,
    )
    try:
        authenticated = load_living_dex_authenticated_causal_examples(store)
        train_lineages = frozenset(item.identity.lineage_sha256 for item in authenticated)
        train_states = frozenset(
            (item.identity.state_sha256, item.identity.envelope_sha256) for item in authenticated
        )
        plan_roots: list[RedLivingDexDevelopmentRoot] = []
        for binding in bindings:
            plan_roots.extend(_load_plan_development_roots(store, binding))
        historical = _deduplicate_roots(plan_roots)
        root_pairs = tuple(
            (root.logical_root_sha256, root.physical_root_sha256) for root in historical
        )
        with claim_first_availability_snapshot_lease(claim_registry) as lease:
            availability = lease.observe(root_pairs)
        available_pairs = {
            (item.logical_root_sha256, item.physical_root_sha256)
            for item in availability.observations
            if item.available
        }
        available = tuple(
            root
            for root in historical
            if (root.logical_root_sha256, root.physical_root_sha256) in available_pairs
        )
        inventory = RedLivingDexDevelopmentSupplyInventory(
            result=result,
            train_lineages=train_lineages,
            train_states=train_states,
            historical_roots=historical,
            available_roots=available,
        )
        if (
            len(train_lineages & {item.lineage_sha256 for item in historical})
            != result.lineage_overlap_with_train
            or len(
                train_states & {(item.state_sha256, item.envelope_sha256) for item in historical}
            )
            != result.state_overlap_with_train
            or tuple(sorted({kind for root in available for kind in root.option_kinds}))
            != result.available_option_kinds
        ):
            raise RedLivingDexDevelopmentSupplyError(
                "development supply private inventory reproduction differs"
            )
        return inventory
    except RedLivingDexDevelopmentSupplyError:
        raise
    except BaseException:
        raise RedLivingDexDevelopmentSupplyError(
            "development supply private inventory authentication failed"
        ) from None


def build_red_living_dex_development_supplement_capabilities(
    capabilities: Sequence[RedLivingDexCausalRootCapability],
) -> tuple[LivingDexDevelopmentSupplementCapability, ...]:
    """Project authenticated Red development edges into the shared planner."""

    if isinstance(capabilities, (str, bytes)) or not isinstance(
        capabilities,
        Sequence,
    ):
        raise TypeError("Red development supplement capabilities need a sequence")
    projected: list[LivingDexDevelopmentSupplementCapability] = []
    for capability in capabilities:
        if not isinstance(capability, RedLivingDexCausalRootCapability):
            raise TypeError("Red development supplement capability differs")
        capability.__post_init__()
        root = capability.root
        if (
            root.cluster_partition != "development"
            or capability.slot.partition is not LivingDexCapturePartition.DEVELOPMENT
        ):
            continue
        if (
            not root.prospective_independence_authenticated
            or root.independence_lineage_sha256 is None
        ):
            raise RedLivingDexDevelopmentSupplyError(
                "Red development supplement lineage is unauthenticated"
            )
        shared = LivingDexClusteredScenarioCapability(
            lineage_sha256=root.independence_lineage_sha256,
            physical_root_sha256=root.root.physical_root_sha256,
            partition="development",
            template_sha256=capability.slot.slot_sha256,
            available_option_kinds=capability.slot.available_option_kinds,
        )
        projected.append(
            LivingDexDevelopmentSupplementCapability(
                lineage_sha256=shared.lineage_sha256,
                physical_root_sha256=shared.physical_root_sha256,
                scenario_sha256=shared.scenario_sha256,
                family_scope_id=capability.slot.family_scope_id,
                location_scope_id=capability.slot.location_scope_id,
                available_option_kinds=shared.available_option_kinds,
            )
        )
    if not projected:
        raise RedLivingDexDevelopmentSupplyError(
            "Red development supplement has no eligible capabilities"
        )
    return tuple(sorted(projected, key=lambda item: item.scenario_sha256))


def _load_plan_development_roots(
    store: PrivateArtifactRoot,
    binding: RedLivingDexClusteredTrainPlanBinding,
) -> tuple[RedLivingDexDevelopmentRoot, ...]:
    if not isinstance(binding, RedLivingDexClusteredTrainPlanBinding):
        raise TypeError("development supply plan binding differs")
    binding.__post_init__()
    record = store.find_sealed_record(
        binding.record_id,
        expected_kind=binding.record_kind,
    )
    if (
        record is None
        or record.summary.manifest_sha256 != binding.plan_manifest_sha256
        or record.summary.record_sha256 != binding.plan_record_sha256
    ):
        raise RedLivingDexDevelopmentSupplyError("development schedule record differs")
    document = record.read()
    schedule = validate_red_living_dex_clustered_private_plan(
        document,
        expected_schedule_sha256=binding.schedule_sha256,
        expected_policy_sha256=binding.policy_sha256,
    )
    assignments = document.get("assignments")
    if not isinstance(assignments, list):
        raise RedLivingDexDevelopmentSupplyError("development schedule assignments differ")
    development = tuple(
        _parse_development_root(item)
        for item in assignments
        if isinstance(item, Mapping) and item.get("partition") == "development"
    )
    if len(development) != schedule.policy.development_scenarios:
        raise RedLivingDexDevelopmentSupplyError("development schedule denominator differs")
    return development


def _parse_development_root(
    value: Mapping[str, object],
) -> RedLivingDexDevelopmentRoot:
    if set(value) != _ASSIGNMENT_FIELDS or value.get("partition") != "development":
        raise RedLivingDexDevelopmentSupplyError("development assignment fields differ")
    kinds = value.get("available_option_kinds")
    if not isinstance(kinds, list) or not kinds:
        raise RedLivingDexDevelopmentSupplyError("development assignment option kinds differ")
    try:
        return RedLivingDexDevelopmentRoot(
            lineage_sha256=value["lineage_sha256"],  # type: ignore[arg-type]
            logical_root_sha256=value["root_consumption_sha256"],  # type: ignore[arg-type]
            physical_root_sha256=value["physical_root_sha256"],  # type: ignore[arg-type]
            state_sha256=value["root_state_sha256"],  # type: ignore[arg-type]
            envelope_sha256=value["root_envelope_sha256"],  # type: ignore[arg-type]
            option_kinds=frozenset(kinds),  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError):
        raise RedLivingDexDevelopmentSupplyError(
            "development assignment identity differs"
        ) from None


def _deduplicate_roots(
    roots: Sequence[RedLivingDexDevelopmentRoot],
) -> tuple[RedLivingDexDevelopmentRoot, ...]:
    if not roots:
        raise RedLivingDexDevelopmentSupplyError("development schedules are empty")
    grouped: dict[tuple[str, str, str, str, str], RedLivingDexDevelopmentRoot] = {}
    for root in roots:
        existing = grouped.get(root.deduplication_key)
        if existing is not None and existing.option_kinds != root.option_kinds:
            raise RedLivingDexDevelopmentSupplyError("duplicate development root semantics differ")
        grouped[root.deduplication_key] = root
    unique = tuple(grouped[key] for key in sorted(grouped))
    lineages = [root.lineage_sha256 for root in unique]
    physical = [root.physical_root_sha256 for root in unique]
    states = [(root.state_sha256, root.envelope_sha256) for root in unique]
    if (
        len(set(lineages)) != len(lineages)
        or len(set(physical)) != len(physical)
        or len(set(states)) != len(states)
    ):
        raise RedLivingDexDevelopmentSupplyError(
            "development roots are not independently identifiable"
        )
    return unique


__all__ = [
    "DEVELOPMENT_SETUP_CENSOR_ALLOWANCE",
    "MINIMUM_DEVELOPMENT_ROOTS",
    "RED_LIVING_DEX_DEVELOPMENT_SUPPLY_RESULT_SCHEMA",
    "RedLivingDexDevelopmentRoot",
    "RedLivingDexDevelopmentSupplyInventory",
    "RedLivingDexDevelopmentSupplyError",
    "RedLivingDexDevelopmentSupplyResult",
    "audit_red_living_dex_development_supply",
    "build_red_living_dex_development_supplement_capabilities",
    "inventory_red_living_dex_development_supply",
]
