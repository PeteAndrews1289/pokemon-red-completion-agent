"""Direct production invocation for one frozen Red causal campaign.

This is the sole controller-capable outer seam for the campaign frozen by
``freeze_red_living_dex_causal_campaign``.  It does not refreeze, preflight, or
select a root.  The immutable campaign supplies the exact provider identity and
ordinal; the current clean CI-qualified consumer supplies the execution source;
and the Red ROM remains unopened until the already durable claim-first runner
asks the cold resolver for a postclaim scope.

The public function accepts no resolver or behavior policy injection.  Recovery
of a terminal setup or causal example therefore constructs no runtime and never
opens the ROM.
"""

from __future__ import annotations

import os
import platform
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstExecutionIdentity,
    ClaimFirstRootPair,
)
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import EmulatorFrameObserver
from pokemon_red_completion.execution_runtime_closure import (
    ExecutionRuntimeClosureError,
    authenticate_execution_runtime_closure,
    require_authenticated_runtime_finder,
    require_loaded_runtime_origins,
    require_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_root,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
)
from pokemon_red_completion.red_living_dex_causal_campaign import (
    RED_LIVING_DEX_CAUSAL_CAMPAIGN_RUNNER_SHA256,
    RedLivingDexCausalCampaignError,
    RedLivingDexCausalCampaignReceipt,
    RedLivingDexCausalExecutionIdentity,
    RedLivingDexFrozenCausalCampaign,
    load_red_living_dex_causal_campaign,
    run_red_living_dex_causal_campaign,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    RedLivingDexClaimedSetupResolver,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RedLivingDexClaimFirstInvocationError,
    RedLivingDexCurrentConsumerBinding,
    RedLivingDexFrozenProducerBinding,
    RedLivingDexProducerSlotLoader,
    authenticate_red_living_dex_producer_slot,
    require_red_living_dex_current_consumer,
)
from pokemon_red_completion.red_living_dex_production_runtime import (
    RedLivingDexFrozenRecipeAccess,
    RedLivingDexProductionRuntimeLimits,
    RedLivingDexProductionSetupResolver,
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
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentity,
    build_runtime_identity_from,
)

_AUTHENTICATED_CONSUMER_AUTHORITY = object()


@dataclass(frozen=True, slots=True)
class RedLivingDexAuthenticatedConsumer:
    """Current-source binding admitted by the exact isolated CLI bootstrap."""

    binding: RedLivingDexCurrentConsumerBinding
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.binding, RedLivingDexCurrentConsumerBinding)
            or self._authority is not _AUTHENTICATED_CONSUMER_AUTHORITY
        ):
            raise RedLivingDexCausalInvocationError("bootstrap_source_authentication")


def bind_red_living_dex_authenticated_consumer(
    binding: RedLivingDexCurrentConsumerBinding,
    *,
    bootstrap_identity: tuple[str, str, int, int],
) -> RedLivingDexAuthenticatedConsumer:
    """Join the fixed script bootstrap result to the typed consumer binding."""

    if not isinstance(binding, RedLivingDexCurrentConsumerBinding):
        raise TypeError("authenticated consumer needs its typed binding")
    binding.__post_init__()
    if bootstrap_identity != (
        binding.source_commit,
        binding.source_bundle_sha256,
        binding.exact_ci_run,
        binding.exact_ci_attempt,
    ):
        raise RedLivingDexCausalInvocationError("bootstrap_source_authentication")
    return RedLivingDexAuthenticatedConsumer(
        binding,
        _AUTHENTICATED_CONSUMER_AUTHORITY,
    )


def authenticate_red_living_dex_current_consumer(
    project_root: Path,
    binding: RedLivingDexCurrentConsumerBinding,
) -> RedLivingDexAuthenticatedConsumer:
    """Authenticate a normal clean published consumer for repeatable development."""

    require_red_living_dex_current_consumer(project_root, binding)
    return RedLivingDexAuthenticatedConsumer(
        binding,
        _AUTHENTICATED_CONSUMER_AUTHORITY,
    )


class RedLivingDexCausalInvocationError(RuntimeError):
    """The direct immutable-campaign consumer failed a sanitized stage."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


@dataclass(slots=True)
class _LateProductionResolver:
    """Load and authenticate Red only when the postclaim runner calls us."""

    rom_path: Path = field(repr=False)
    producer_execution_identity: RedLivingDexSetupExecutionIdentity = field(repr=False)
    runtime_limits: RedLivingDexProductionRuntimeLimits | None = field(
        default=None,
        repr=False,
    )
    frame_observer: EmulatorFrameObserver | None = field(default=None, repr=False)
    _delegate: RedLivingDexProductionSetupResolver | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __call__(
        self,
        frozen: RedLivingDexFrozenRecipeAccess,
        root: RedLivingDexAuthenticatedSetupRoot,
        pair_claim: ClaimFirstRootPair,
        *,
        meter: RedLivingDexSetupEffectMeter,
    ):  # type: ignore[no-untyped-def]
        if self._delegate is None:
            if not isinstance(
                self.producer_execution_identity,
                RedLivingDexSetupExecutionIdentity,
            ):
                raise RedLivingDexCausalInvocationError("runtime_identity_authentication")
            self._delegate = RedLivingDexProductionSetupResolver(
                rom_path=self.rom_path,
                rom_bytes=_read_stable_red_rom(self.rom_path),
                producer_execution_identity=self.producer_execution_identity,
                runtime_limits=self.runtime_limits,
                frame_observer=self.frame_observer,
            )
        return self._delegate(
            frozen,
            root,
            pair_claim,
            meter=meter,
        )


RedLivingDexLateProductionResolver = _LateProductionResolver


def execute_red_living_dex_causal_campaign(
    project_root: Path,
    store: PrivateArtifactRoot,
    *,
    consumer: RedLivingDexAuthenticatedConsumer,
    producer_slot_loader: RedLivingDexProducerSlotLoader,
    rom_path: Path,
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexCausalCampaignReceipt:
    """Execute or terminally recover the one immutable Red train campaign."""

    if not isinstance(project_root, Path):
        raise TypeError("causal invocation needs a project Path")
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("causal invocation needs its private artifact root")
    if not isinstance(consumer, RedLivingDexAuthenticatedConsumer):
        raise TypeError("causal invocation needs its authenticated consumer")
    consumer.__post_init__()
    if not callable(producer_slot_loader):
        raise TypeError("causal invocation needs one selected-slot loader")
    if not isinstance(rom_path, Path):
        raise TypeError("causal invocation needs its ROM Path")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("causal invocation needs the comprehensive effect meter")

    try:
        current_consumer = consumer.binding
        claim_registry = fixed_account_claim_registry_root()
        plan = load_red_living_dex_causal_campaign(store)
        producer = _producer_binding(plan)
        loaded, plan_document = authenticate_red_living_dex_producer_slot(
            producer,
            producer_slot_loader,
        )
        frozen = authenticate_frozen_red_living_dex_setup_slot(
            plan_document,
            expected_plan_sha256=producer.producer_plan_sha256,
            ordinal=producer.ordinal,
            root=loaded.root,
        )
        _require_plan_join(plan, frozen, root=loaded.root)
        runtime_identity_sha256 = _authenticate_current_execution_runtime(
            project_root,
            loaded.record,
        )
        setup_identity = _current_setup_execution_identity(
            plan,
            consumer=current_consumer,
        )
        execution_identity = RedLivingDexCausalExecutionIdentity(
            setup_execution_identity=setup_identity,
            campaign_sha256=plan.campaign_sha256,
            frozen_campaign_runner_sha256=plan.causal_runner_sha256,
        )
        resolver = _LateProductionResolver(
            rom_path=rom_path,
            producer_execution_identity=frozen.producer_execution_identity(),
        )
        if not isinstance(resolver, RedLivingDexClaimedSetupResolver):
            raise RedLivingDexCausalInvocationError("runtime_identity_authentication")
        previous_record = loaded.record

        def load_plan() -> Mapping[str, object]:
            nonlocal previous_record
            if load_red_living_dex_causal_campaign(store) != plan:
                raise RedLivingDexCausalInvocationError("campaign_reauthentication")
            reopened, document = authenticate_red_living_dex_producer_slot(
                producer,
                producer_slot_loader,
            )
            if reopened.record is previous_record or reopened.root != loaded.root:
                raise RedLivingDexCausalInvocationError("producer_reauthentication")
            if _sealed_runtime_identity_sha256(reopened.record) != (runtime_identity_sha256):
                raise RedLivingDexCausalInvocationError("runtime_identity_authentication")
            previous_record = reopened.record
            return document

        return run_red_living_dex_causal_campaign(
            plan,
            execution_identity=execution_identity,
            store=store,
            plan_loader=load_plan,
            frozen=frozen,
            root=loaded.root,
            resolver=resolver,
            meter=meter,
            claim_registry=claim_registry,
        )
    except RedLivingDexCausalInvocationError:
        raise
    except RedLivingDexClaimFirstInvocationError as error:
        raise RedLivingDexCausalInvocationError(error.stage) from None
    except RedLivingDexCausalCampaignError:
        raise RedLivingDexCausalInvocationError("campaign_authentication") from None
    except Exception:
        raise RedLivingDexCausalInvocationError("execution_failed") from None


def _authenticate_current_execution_runtime(
    project_root: Path,
    record: PrivateSealedRecord,
) -> str:
    """Bind the clean staged closure to the producer's frozen PyBoy identity."""

    return authenticate_red_living_dex_execution_runtime(
        project_root,
        _sealed_runtime_identity_sha256(record),
    ).sha256


def authenticate_red_living_dex_execution_runtime(
    project_root: Path,
    expected_runtime_identity_sha256: str,
) -> RuntimeIdentity:
    """Return the staged runtime after matching one frozen path-free digest."""

    try:
        expected = require_sha256(expected_runtime_identity_sha256)
        original_site = (project_root / ".venv/lib/python3.14/site-packages").resolve(strict=True)
        candidates = tuple(
            Path(item).resolve(strict=True)
            for item in sys.path
            if isinstance(item, str)
            and item
            and Path(item).is_absolute()
            and item.endswith("/venv/lib/python3.14/site-packages")
        )
        staged = tuple(path for path in candidates if path != original_site)
        if len(staged) != 1 or original_site in candidates:
            raise ExecutionRuntimeClosureError("runtime stage path differs")
        closure = authenticate_execution_runtime_closure(staged[0])
        require_authenticated_runtime_finder(closure)
        require_loaded_runtime_origins(closure)
        distribution = metadata.PathDistribution(staged[0] / "pyboy-2.7.0.dist-info")
        identity = build_runtime_identity_from(
            python_executable=sys.executable,
            python_implementation=platform.python_implementation(),
            python_version=platform.python_version(),
            pyboy_distribution=distribution,
        )
        if identity.sha256 != expected:
            raise ExecutionRuntimeClosureError("staged PyBoy identity differs from sealed producer")
        return identity
    except RedLivingDexCausalInvocationError:
        raise
    except BaseException:
        raise RedLivingDexCausalInvocationError("runtime_identity_authentication") from None


def _sealed_runtime_identity_sha256(record: PrivateSealedRecord) -> str:
    try:
        document = record.read()
        return require_sha256(document.get("runtime_identity_sha256"))
    except BaseException:
        raise RedLivingDexCausalInvocationError("runtime_identity_authentication") from None


def _producer_binding(
    plan: RedLivingDexFrozenCausalCampaign,
) -> RedLivingDexFrozenProducerBinding:
    outer = plan.outer_execution_identity
    return RedLivingDexFrozenProducerBinding(
        producer_plan_sha256=plan.producer_plan_sha256,
        producer_private_plan_sha256=outer.producer_private_plan_sha256,
        producer_manifest_sha256=outer.producer_manifest_sha256,
        ordinal=plan.ordinal,
    )


def _current_setup_execution_identity(
    plan: RedLivingDexFrozenCausalCampaign,
    *,
    consumer: RedLivingDexCurrentConsumerBinding,
) -> ClaimFirstExecutionIdentity:
    frozen = plan.outer_execution_identity
    if (
        frozen.title_adapter_sha256 != RED_LIVING_DEX_TITLE_ADAPTER_SHA256
        or frozen.runtime_factory_sha256 != RED_LIVING_DEX_RUNTIME_FACTORY_SHA256
        or plan.causal_runner_sha256 != RED_LIVING_DEX_CAUSAL_CAMPAIGN_RUNNER_SHA256
    ):
        raise RedLivingDexCausalInvocationError("campaign_authentication")
    return ClaimFirstExecutionIdentity(
        source_commit=consumer.source_commit,
        source_bundle_sha256=consumer.source_bundle_sha256,
        exact_ci_run=consumer.exact_ci_run,
        exact_ci_attempt=consumer.exact_ci_attempt,
        producer_execution_identity_sha256=(plan.producer_execution_identity_sha256),
        producer_plan_sha256=plan.producer_plan_sha256,
        producer_private_plan_sha256=frozen.producer_private_plan_sha256,
        producer_manifest_sha256=frozen.producer_manifest_sha256,
        slot_sha256=plan.slot_sha256,
        recipe_sha256=plan.recipe_sha256,
        logical_root_sha256=plan.logical_root_sha256,
        physical_root_sha256=plan.physical_root_sha256,
        title_adapter_sha256=RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
        runtime_factory_sha256=RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
        runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    )


def _require_plan_join(
    plan: RedLivingDexFrozenCausalCampaign,
    frozen: FrozenRedLivingDexSetupSlot,
    *,
    root: RedLivingDexAuthenticatedSetupRoot,
) -> None:
    if (
        frozen.ordinal != plan.ordinal
        or frozen.producer_plan_sha256 != plan.producer_plan_sha256
        or frozen.producer_execution_identity_sha256 != plan.producer_execution_identity_sha256
        or frozen.recipe_sha256 != plan.recipe_sha256
        or frozen.slot_sha256 != plan.slot_sha256
        or frozen.logical_root_sha256 != plan.logical_root_sha256
        or frozen.physical_root_sha256 != plan.physical_root_sha256
        or frozen.root_state_sha256 != plan.root_state_sha256
        or frozen.root_envelope_sha256 != plan.root_envelope_sha256
        or root.root_consumption_sha256 != plan.logical_root_sha256
        or root.physical_root_sha256 != plan.physical_root_sha256
        or root.state_sha256 != plan.root_state_sha256
        or root.envelope_sha256 != plan.root_envelope_sha256
    ):
        raise RedLivingDexCausalInvocationError("selected_root_authentication")


def _read_stable_red_rom(path: Path) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        named = path.lstat()
        resolved = path.resolve(strict=True)
        if (
            not path.is_absolute()
            or path.is_symlink()
            or resolved != path
            or not stat.S_ISREG(named.st_mode)
            or named.st_nlink != 1
            or named.st_uid != os.getuid()
            or stat.S_IMODE(named.st_mode) & 0o022
            or named.st_size != POKEMON_RED_US_REV_0.size_bytes
        ):
            raise OSError("ROM path differs")
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != named.st_dev
            or opened.st_ino != named.st_ino
            or opened.st_size != named.st_size
            or opened.st_mtime_ns != named.st_mtime_ns
            or opened.st_ctime_ns != named.st_ctime_ns
        ):
            raise OSError("ROM changed before open")
        payload = os.read(descriptor, opened.st_size + 1)
        finished = os.fstat(descriptor)
        if (
            len(payload) != opened.st_size
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise OSError("ROM changed during read")
        return payload
    except OSError:
        raise RedLivingDexCausalInvocationError("rom_authentication") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


__all__ = [
    "RedLivingDexAuthenticatedConsumer",
    "RedLivingDexCausalInvocationError",
    "RedLivingDexLateProductionResolver",
    "authenticate_red_living_dex_execution_runtime",
    "authenticate_red_living_dex_current_consumer",
    "bind_red_living_dex_authenticated_consumer",
    "execute_red_living_dex_causal_campaign",
]
