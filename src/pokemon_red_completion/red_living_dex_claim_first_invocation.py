"""Current-source admission for one Red living-Dex setup invocation.

The frozen producer plan predates the current claim-first consumer.  This
module joins those two immutable identities without replaying the old
all-roots preflight: authenticate the clean published consumer and its exact
push CI, reopen the sealed producer record, load exactly one selected root,
and construct the only permitted Red production resolver only in the
explicit execution entrypoint.

The default preflight is deliberately incapable of claiming a root,
constructing a resolver, opening an emulator, executing a provider, choosing
an option, recording an outcome, or fitting a model.
"""

from __future__ import annotations

import http.client
import json
import re
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstExecutionIdentity,
    observe_claim_first_pair_availability,
)
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
    validate_private_record,
)
from pokemon_red_completion.provenance import (
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    RedLivingDexClaimedSetupResolver,
    RedLivingDexClaimFirstReceipt,
    run_red_living_dex_claim_first_setup_slot,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_admission import (
    FrozenRedLivingDexSetupSlot,
    authenticate_frozen_red_living_dex_setup_slot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupExecutionIdentity,
)

RED_LIVING_DEX_CLAIM_FIRST_INVOCATION_PREFLIGHT_SCHEMA = (
    "pokemon.red.living-dex-claim-first-invocation-preflight.v1"
)
RED_LIVING_DEX_PROVIDER_PLAN_SCHEMA = (
    "pokemon.red.private-living-dex-provider-plan.v1"
)
RED_LIVING_DEX_PROVIDER_PLAN_RECORD_ID = "red-living-dex-provider-plan-v1"
RED_LIVING_DEX_PROVIDER_PLAN_RECORD_KIND = "red-living-dex-provider-plan-v1"

_GITHUB_HOST = "api.github.com"
_GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
_CI_WORKFLOW_NAME = "CI"
_CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
_GITHUB_API_VERSION = "2022-11-28"
_MAXIMUM_GITHUB_RESPONSE_BYTES = 256 * 1024
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PRIVATE_PLAN_KEYS = frozenset(
    {
        "context_catalog_sha256",
        "context_plan_sha256",
        "controller_actions",
        "emulator_frames",
        "execution_identity",
        "execution_identity_sha256",
        "freeze",
        "freeze_sha256",
        "goal_registry_sha256",
        "model_fits",
        "model_predictions",
        "outcomes",
        "private_plan_sha256",
        "provider_executions",
        "recipe_plan",
        "recipe_plan_sha256",
        "root_claims",
        "route_registry_sha256",
        "rom_sha256",
        "runtime_identity_sha256",
        "schema",
        "source_catalog_partition_reused_as_prospective_label",
        "source_bundle_sha256",
        "source_commit",
        "status",
        "teacher_queries",
    }
)
_ZERO_EFFECT_KEYS = (
    "controller_actions",
    "emulator_frames",
    "model_fits",
    "model_predictions",
    "outcomes",
    "provider_executions",
    "root_claims",
    "teacher_queries",
)


class RedLivingDexClaimFirstInvocationError(RuntimeError):
    """One path-free invocation-admission stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


@dataclass(frozen=True, slots=True)
class RedLivingDexCurrentConsumerBinding:
    """Expected clean published consumer and exact successful push CI."""

    source_commit: str
    source_bundle_sha256: str
    exact_ci_run: int
    exact_ci_attempt: int

    def __post_init__(self) -> None:
        if not isinstance(self.source_commit, str) or _SHA1.fullmatch(
            self.source_commit
        ) is None:
            raise RedLivingDexClaimFirstInvocationError("current_source_authentication")
        _require_sha256(self.source_bundle_sha256, "current_source_authentication")
        if (
            type(self.exact_ci_run) is not int  # noqa: E721
            or self.exact_ci_run <= 0
            or type(self.exact_ci_attempt) is not int  # noqa: E721
            or self.exact_ci_attempt <= 0
        ):
            raise RedLivingDexClaimFirstInvocationError("current_ci_authentication")


@dataclass(frozen=True, slots=True)
class RedLivingDexFrozenProducerBinding:
    """Expected sealed producer record and one selected recipe ordinal."""

    producer_plan_sha256: str = field(repr=False)
    producer_private_plan_sha256: str = field(repr=False)
    producer_manifest_sha256: str = field(repr=False)
    ordinal: int

    def __post_init__(self) -> None:
        for value in (
            self.producer_plan_sha256,
            self.producer_private_plan_sha256,
            self.producer_manifest_sha256,
        ):
            _require_sha256(value, "immutable_producer_authentication")
        if type(self.ordinal) is not int or not 0 <= self.ordinal < 15:  # noqa: E721
            raise RedLivingDexClaimFirstInvocationError("selected_slot_authentication")


@dataclass(frozen=True, slots=True)
class RedLivingDexLoadedProducerSlot:
    """One freshly reopened sealed record plus exactly one root byte pair."""

    record: PrivateSealedRecord = field(repr=False)
    root: RedLivingDexAuthenticatedSetupRoot = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.record, PrivateSealedRecord):
            raise TypeError("producer slot loader must return a sealed record")
        if not isinstance(self.root, RedLivingDexAuthenticatedSetupRoot):
            raise TypeError("producer slot loader must return one authenticated root")
        self.root.__post_init__()


RedLivingDexProducerSlotLoader = Callable[[int], RedLivingDexLoadedProducerSlot]


@dataclass(frozen=True, slots=True)
class RedLivingDexClaimFirstPreflightReceipt:
    """Path-free proof that one selected slot can reach the atomic claim gate."""

    def public_dict(self) -> dict[str, object]:
        return {
            "behavior_draws": 0,
            "claim_registry_observations": 1,
            "controller_actions": 0,
            "current_consumer_bound": True,
            "emulator_frames": 0,
            "exact_ci_bound": True,
            "learner_labels": 0,
            "learner_outcomes": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "producer_executions": 0,
            "producer_record_reads": 1,
            "resolver_constructions": 0,
            "root_claims": 0,
            "schema": RED_LIVING_DEX_CLAIM_FIRST_INVOCATION_PREFLIGHT_SCHEMA,
            "selected_root_reads": 1,
            "selected_slots": 1,
            "setup_campaign_calls": 0,
            "sibling_root_reads": 0,
            "status": "one_slot_ready_before_claim_or_runtime",
            "teacher_queries": 0,
        }


@dataclass(frozen=True, slots=True)
class _AuthenticatedInvocation:
    frozen: FrozenRedLivingDexSetupSlot
    root: RedLivingDexAuthenticatedSetupRoot = field(repr=False)
    outer_identity: ClaimFirstExecutionIdentity = field(repr=False)
    initial_record: PrivateSealedRecord = field(repr=False)


def preflight_red_living_dex_claim_first_invocation(
    project_root: Path,
    *,
    consumer: RedLivingDexCurrentConsumerBinding,
    producer: RedLivingDexFrozenProducerBinding,
    producer_slot_loader: RedLivingDexProducerSlotLoader,
    claim_registry: Path,
) -> RedLivingDexClaimFirstPreflightReceipt:
    """Authenticate one selected slot without a claim or runtime-capable object."""

    prepared = _authenticate_invocation(
        project_root,
        consumer=consumer,
        producer=producer,
        producer_slot_loader=producer_slot_loader,
    )
    _require_current_consumer(project_root, consumer)
    try:
        available = observe_claim_first_pair_availability(
            claim_registry,
            prepared.frozen.logical_root_sha256,
            prepared.frozen.physical_root_sha256,
        )
    except BaseException:
        raise RedLivingDexClaimFirstInvocationError("claim_registry_authentication") from None
    if not available:
        raise RedLivingDexClaimFirstInvocationError("selected_root_unavailable")
    return RedLivingDexClaimFirstPreflightReceipt()


def execute_red_living_dex_claim_first_invocation(
    project_root: Path,
    store: PrivateArtifactRoot,
    *,
    consumer: RedLivingDexCurrentConsumerBinding,
    producer: RedLivingDexFrozenProducerBinding,
    producer_slot_loader: RedLivingDexProducerSlotLoader,
    claim_registry: Path,
    rom_path: Path,
    rom_bytes: bytes,
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexClaimFirstReceipt:
    """Execute exactly one slot through the fixed production resolver.

    There is intentionally no resolver or resolver-factory parameter.  A
    separately authenticated outer bootstrap supplies private inputs; this
    boundary owns the only title adapter permitted to cross the atomic claim.
    """

    prepared = _authenticate_invocation(
        project_root,
        consumer=consumer,
        producer=producer,
        producer_slot_loader=producer_slot_loader,
    )
    _require_current_consumer(project_root, consumer)
    resolver = _build_production_resolver(
        rom_path=rom_path,
        rom_bytes=rom_bytes,
        producer_execution_identity=prepared.frozen.producer_execution_identity(),
    )
    previous_record = prepared.initial_record

    def load_plan() -> Mapping[str, object]:
        nonlocal previous_record
        loaded, plan = _load_and_authenticate_producer_slot(
            producer,
            producer_slot_loader,
        )
        if loaded.record is previous_record or loaded.root != prepared.root:
            raise RedLivingDexClaimFirstInvocationError(
                "postclaim_producer_reauthentication"
            )
        previous_record = loaded.record
        return plan

    return run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=load_plan,
        expected_producer_plan_sha256=producer.producer_plan_sha256,
        ordinal=producer.ordinal,
        root=prepared.root,
        outer_execution_identity=prepared.outer_identity,
        resolver=resolver,
        meter=meter,
        claim_registry=claim_registry,
    )


def _build_production_resolver(
    *,
    rom_path: Path,
    rom_bytes: bytes,
    producer_execution_identity: RedLivingDexSetupExecutionIdentity,
) -> RedLivingDexClaimedSetupResolver:
    """Import and construct the Red runtime only after every preclaim join."""

    from pokemon_red_completion.red_living_dex_production_runtime import (
        RedLivingDexProductionSetupResolver,
    )

    return RedLivingDexProductionSetupResolver(
        rom_path=rom_path,
        rom_bytes=rom_bytes,
        producer_execution_identity=producer_execution_identity,
    )


def _authenticate_invocation(
    project_root: Path,
    *,
    consumer: RedLivingDexCurrentConsumerBinding,
    producer: RedLivingDexFrozenProducerBinding,
    producer_slot_loader: RedLivingDexProducerSlotLoader,
) -> _AuthenticatedInvocation:
    if not isinstance(project_root, Path):
        raise TypeError("claim-first invocation needs a project Path")
    if not isinstance(consumer, RedLivingDexCurrentConsumerBinding):
        raise TypeError("claim-first invocation needs a current consumer binding")
    consumer.__post_init__()
    if not isinstance(producer, RedLivingDexFrozenProducerBinding):
        raise TypeError("claim-first invocation needs a frozen producer binding")
    producer.__post_init__()
    if not callable(producer_slot_loader):
        raise TypeError("claim-first invocation needs one producer-slot loader")
    _require_current_consumer(project_root, consumer)
    loaded, plan = _load_and_authenticate_producer_slot(producer, producer_slot_loader)
    try:
        frozen = authenticate_frozen_red_living_dex_setup_slot(
            plan,
            expected_plan_sha256=producer.producer_plan_sha256,
            ordinal=producer.ordinal,
            root=loaded.root,
        )
        outer = ClaimFirstExecutionIdentity(
            source_commit=consumer.source_commit,
            source_bundle_sha256=consumer.source_bundle_sha256,
            exact_ci_run=consumer.exact_ci_run,
            exact_ci_attempt=consumer.exact_ci_attempt,
            producer_execution_identity_sha256=(
                frozen.producer_execution_identity_sha256
            ),
            producer_plan_sha256=frozen.producer_plan_sha256,
            producer_private_plan_sha256=producer.producer_private_plan_sha256,
            producer_manifest_sha256=producer.producer_manifest_sha256,
            slot_sha256=frozen.slot_sha256,
            recipe_sha256=frozen.recipe_sha256,
            logical_root_sha256=frozen.logical_root_sha256,
            physical_root_sha256=frozen.physical_root_sha256,
            title_adapter_sha256=RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
            runtime_factory_sha256=RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
            runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
        )
    except RedLivingDexClaimFirstInvocationError:
        raise
    except BaseException:
        raise RedLivingDexClaimFirstInvocationError("selected_slot_authentication") from None
    return _AuthenticatedInvocation(frozen, loaded.root, outer, loaded.record)


def _load_and_authenticate_producer_slot(
    producer: RedLivingDexFrozenProducerBinding,
    loader: RedLivingDexProducerSlotLoader,
) -> tuple[RedLivingDexLoadedProducerSlot, Mapping[str, object]]:
    try:
        loaded = loader(producer.ordinal)
        if not isinstance(loaded, RedLivingDexLoadedProducerSlot):
            raise TypeError("producer slot loader returned another type")
        loaded.__post_init__()
        summary = loaded.record.summary
        document = loaded.record.read()
        validate_private_record(document)
        if (
            set(document) != _PRIVATE_PLAN_KEYS
            or summary.record_id != RED_LIVING_DEX_PROVIDER_PLAN_RECORD_ID
            or summary.kind != RED_LIVING_DEX_PROVIDER_PLAN_RECORD_KIND
            or summary.manifest_sha256 != producer.producer_manifest_sha256
            or document.get("private_plan_sha256")
            != producer.producer_private_plan_sha256
        ):
            raise ValueError("sealed producer record differs")
        payload = dict(document)
        embedded_private_plan = payload.pop("private_plan_sha256")
        if canonical_sha256(payload) != embedded_private_plan:
            raise ValueError("sealed producer payload differs")
        plan = _mapping(document.get("recipe_plan"))
        execution = _mapping(document.get("execution_identity"))
        freeze = _mapping(document.get("freeze"))
        if (
            document.get("schema") != RED_LIVING_DEX_PROVIDER_PLAN_SCHEMA
            or document.get("status")
            != "frozen_before_claim_controller_input_outcome_or_fit"
            or document.get("source_catalog_partition_reused_as_prospective_label")
            is not False
            or any(document.get(key) != 0 for key in _ZERO_EFFECT_KEYS)
            or document.get("rom_sha256") != POKEMON_RED_US_REV_0.sha256
            or canonical_sha256(plan) != producer.producer_plan_sha256
            or document.get("recipe_plan_sha256") != producer.producer_plan_sha256
            or canonical_sha256(execution)
            != document.get("execution_identity_sha256")
            or document.get("source_commit") != execution.get("source_commit")
            or document.get("source_bundle_sha256")
            != execution.get("source_bundle_sha256")
            or plan.get("execution_identity") != execution
            or plan.get("execution_identity_sha256")
            != document.get("execution_identity_sha256")
            or freeze.get("recipe_plan_sha256") != producer.producer_plan_sha256
            or canonical_sha256(freeze) != document.get("freeze_sha256")
        ):
            raise ValueError("sealed producer joins differ")
        return loaded, MappingProxyType(dict(plan))
    except RedLivingDexClaimFirstInvocationError:
        raise
    except BaseException:
        raise RedLivingDexClaimFirstInvocationError(
            "immutable_producer_authentication"
        ) from None


def _require_current_consumer(
    project_root: Path,
    expected: RedLivingDexCurrentConsumerBinding,
) -> None:
    try:
        identity = detect_source_identity(project_root)
        require_clean_source(identity)
        require_published_source(project_root, identity)
        if (
            identity.git_commit != expected.source_commit
            or working_source_bundle_sha256(project_root)
            != expected.source_bundle_sha256
        ):
            raise ValueError("current source differs")
    except BaseException:
        raise RedLivingDexClaimFirstInvocationError("current_source_authentication") from None
    _require_exact_green_ci(expected)


def _require_exact_green_ci(expected: RedLivingDexCurrentConsumerBinding) -> None:
    path = (
        f"/repos/{_GITHUB_REPOSITORY}/actions/runs/{expected.exact_ci_run}"
        f"/attempts/{expected.exact_ci_attempt}"
    )
    connection: http.client.HTTPSConnection | None = None
    try:
        connection = http.client.HTTPSConnection(
            _GITHUB_HOST,
            timeout=10,
            context=ssl.create_default_context(),
        )
        connection.request(
            "GET",
            path,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "pokemon-red-completion-agent",
                "X-GitHub-Api-Version": _GITHUB_API_VERSION,
            },
        )
        response = connection.getresponse()
        payload = response.read(_MAXIMUM_GITHUB_RESPONSE_BYTES + 1)
        if response.status != 200 or len(payload) > _MAXIMUM_GITHUB_RESPONSE_BYTES:
            raise ValueError("CI response differs")
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
        )
    except BaseException:
        raise RedLivingDexClaimFirstInvocationError("current_ci_authentication") from None
    finally:
        if connection is not None:
            connection.close()
    _require_exact_green_ci_document(expected, document)


def _require_exact_green_ci_document(
    expected: RedLivingDexCurrentConsumerBinding,
    document: object,
) -> None:
    repository = document.get("repository") if isinstance(document, Mapping) else None
    expected_url = (
        f"https://github.com/{_GITHUB_REPOSITORY}/actions/runs/{expected.exact_ci_run}"
    )
    if (
        not isinstance(document, Mapping)
        or document.get("id") != expected.exact_ci_run
        or document.get("run_attempt") != expected.exact_ci_attempt
        or document.get("head_sha") != expected.source_commit
        or document.get("status") != "completed"
        or document.get("conclusion") != "success"
        or document.get("name") != _CI_WORKFLOW_NAME
        or document.get("path") != _CI_WORKFLOW_PATH
        or document.get("event") != "push"
        or document.get("html_url") != expected_url
        or not isinstance(repository, Mapping)
        or repository.get("full_name") != _GITHUB_REPOSITORY
    ):
        raise RedLivingDexClaimFirstInvocationError("current_ci_authentication")


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("producer record field is not a mapping")
    return dict(value)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _require_sha256(value: object, stage: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexClaimFirstInvocationError(stage)
    return value


__all__ = [
    "RED_LIVING_DEX_CLAIM_FIRST_INVOCATION_PREFLIGHT_SCHEMA",
    "RED_LIVING_DEX_PROVIDER_PLAN_RECORD_ID",
    "RED_LIVING_DEX_PROVIDER_PLAN_RECORD_KIND",
    "RedLivingDexClaimFirstInvocationError",
    "RedLivingDexClaimFirstPreflightReceipt",
    "RedLivingDexCurrentConsumerBinding",
    "RedLivingDexFrozenProducerBinding",
    "RedLivingDexLoadedProducerSlot",
    "RedLivingDexProducerSlotLoader",
    "execute_red_living_dex_claim_first_invocation",
    "preflight_red_living_dex_claim_first_invocation",
]
