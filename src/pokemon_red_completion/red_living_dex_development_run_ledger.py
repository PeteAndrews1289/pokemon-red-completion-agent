"""Durable per-root terminals for the repeatable Red development loop."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_clustered_development_execution import (
    RedLivingDexClusteredDevelopmentReceipt,
)
from pokemon_red_completion.red_living_dex_development_batch import (
    RedLivingDexDevelopmentBatchAssignment,
)

RED_LIVING_DEX_DEVELOPMENT_RUN_TERMINAL_SCHEMA = (
    "pokemon.red.private-repeatable-living-dex-development-terminal.v1"
)
_KIND = "red_living_dex_repeatable_development_terminal"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexDevelopmentRunLedgerError(RuntimeError):
    """A repeatable case terminal is absent, ambiguous, or altered."""


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentRunTerminal:
    logical_root_sha256: str
    physical_root_sha256: str
    private_plan_sha256: str
    ordinal: int
    setup_status: str
    development_status: str | None
    development_disposition: str | None
    receipt_sha256: str
    retry_allowed: bool = False

    def __post_init__(self) -> None:
        for value in (
            self.logical_root_sha256,
            self.physical_root_sha256,
            self.private_plan_sha256,
            self.receipt_sha256,
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise RedLivingDexDevelopmentRunLedgerError(
                    "development run terminal identity differs"
                )
        if (
            self.logical_root_sha256 == self.physical_root_sha256
            or type(self.ordinal) is not int  # noqa: E721
            or self.ordinal < 0
            or not isinstance(self.setup_status, str)
            or not self.setup_status
            or (self.development_status is None)
            != (self.development_disposition is None)
            or (
                self.development_status is not None
                and (not self.development_status or not self.development_disposition)
            )
            or self.retry_allowed
        ):
            raise RedLivingDexDevelopmentRunLedgerError(
                "development run terminal fields differ"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "development_disposition": self.development_disposition,
            "development_status": self.development_status,
            "logical_root_sha256": self.logical_root_sha256,
            "ordinal": self.ordinal,
            "physical_root_sha256": self.physical_root_sha256,
            "private_plan_sha256": self.private_plan_sha256,
            "receipt_sha256": self.receipt_sha256,
            "retry_allowed": self.retry_allowed,
            "schema": RED_LIVING_DEX_DEVELOPMENT_RUN_TERMINAL_SCHEMA,
            "setup_status": self.setup_status,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "development_status": self.development_status,
            "path_fields": 0,
            "retry_allowed": False,
            "schema": "pokemon.red.repeatable-living-dex-development-terminal.v1",
            "setup_status": self.setup_status,
            "terminal_retained": True,
        }


def find_red_living_dex_development_run_terminal(
    store: PrivateArtifactRoot,
    assignment: RedLivingDexDevelopmentBatchAssignment,
) -> RedLivingDexDevelopmentRunTerminal | None:
    """Return the exact terminal for one root, if the outer runner retained it."""

    _validate_inputs(store, assignment)
    record = store.find_sealed_record(_record_id(assignment), expected_kind=_KIND)
    if record is None:
        return None
    document = record.read()
    try:
        terminal = RedLivingDexDevelopmentRunTerminal(
            logical_root_sha256=_text(document, "logical_root_sha256"),
            physical_root_sha256=_text(document, "physical_root_sha256"),
            private_plan_sha256=_text(document, "private_plan_sha256"),
            ordinal=_integer(document, "ordinal"),
            setup_status=_text(document, "setup_status"),
            development_status=_optional_text(document, "development_status"),
            development_disposition=_optional_text(
                document,
                "development_disposition",
            ),
            receipt_sha256=_text(document, "receipt_sha256"),
            retry_allowed=_false(document, "retry_allowed"),
        )
    except (KeyError, TypeError, ValueError):
        raise RedLivingDexDevelopmentRunLedgerError(
            "stored development run terminal differs"
        ) from None
    if terminal.private_dict() != dict(document) or not _matches(terminal, assignment):
        raise RedLivingDexDevelopmentRunLedgerError(
            "stored development run terminal differs"
        )
    return terminal


def retain_red_living_dex_development_run_terminal(
    store: PrivateArtifactRoot,
    assignment: RedLivingDexDevelopmentBatchAssignment,
    receipt: RedLivingDexClusteredDevelopmentReceipt,
) -> RedLivingDexDevelopmentRunTerminal:
    """Idempotently close one root after its inner journals have returned."""

    _validate_inputs(store, assignment)
    if not isinstance(receipt, RedLivingDexClusteredDevelopmentReceipt):
        raise TypeError("development run ledger needs its typed receipt")
    receipt.__post_init__()
    if (
        receipt.selection.ordinal != assignment.ordinal
        or receipt.selection.private_plan_sha256
        != assignment.binding.private_plan_sha256
        or receipt.selection.logical_root_sha256
        != assignment.root.root_consumption_sha256
        or receipt.selection.physical_root_sha256
        != assignment.root.physical_root_sha256
    ):
        raise RedLivingDexDevelopmentRunLedgerError(
            "development run receipt belongs to another root"
        )
    development = receipt.development
    terminal = RedLivingDexDevelopmentRunTerminal(
        logical_root_sha256=assignment.root.root_consumption_sha256,
        physical_root_sha256=assignment.root.physical_root_sha256,
        private_plan_sha256=assignment.binding.private_plan_sha256,
        ordinal=assignment.ordinal,
        setup_status=receipt.setup.terminal.status.value,
        development_status=(
            None if development is None else development.terminal.status.value
        ),
        development_disposition=(
            None if development is None else development.disposition.value
        ),
        receipt_sha256=canonical_sha256(receipt.public_dict()),
    )
    existing = find_red_living_dex_development_run_terminal(store, assignment)
    if existing is not None:
        if existing != terminal:
            raise RedLivingDexDevelopmentRunLedgerError(
                "development run terminal conflicts"
            )
        return existing
    record = store.publish_sealed_record(
        _record_id(assignment),
        kind=_KIND,
        record=terminal.private_dict(),
    )
    if record.read() != terminal.private_dict():
        raise RedLivingDexDevelopmentRunLedgerError(
            "development run terminal did not round-trip"
        )
    return terminal


def _record_id(assignment: RedLivingDexDevelopmentBatchAssignment) -> str:
    identity = canonical_sha256(
        {
            "logical_root_sha256": assignment.root.root_consumption_sha256,
            "physical_root_sha256": assignment.root.physical_root_sha256,
            "schema": "pokemon.red.repeatable-living-dex-development-root.v1",
        }
    )
    return f"rlddr-terminal-{identity}"


def _matches(
    terminal: RedLivingDexDevelopmentRunTerminal,
    assignment: RedLivingDexDevelopmentBatchAssignment,
) -> bool:
    return (
        terminal.logical_root_sha256 == assignment.root.root_consumption_sha256
        and terminal.physical_root_sha256 == assignment.root.physical_root_sha256
        and terminal.private_plan_sha256 == assignment.binding.private_plan_sha256
        and terminal.ordinal == assignment.ordinal
    )


def _validate_inputs(
    store: PrivateArtifactRoot,
    assignment: RedLivingDexDevelopmentBatchAssignment,
) -> None:
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("development run ledger needs a private store")
    if not isinstance(assignment, RedLivingDexDevelopmentBatchAssignment):
        raise TypeError("development run ledger needs one assignment")
    assignment.__post_init__()


def _text(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(key)
    return value


def _optional_text(document: dict[str, object], key: str) -> str | None:
    value = document.get(key)
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(key)
    return value


def _integer(document: dict[str, object], key: str) -> int:
    value = document.get(key)
    if type(value) is not int:  # noqa: E721
        raise ValueError(key)
    return value


def _false(document: dict[str, object], key: str) -> bool:
    value = document.get(key)
    if value is not False:
        raise ValueError(key)
    return False


__all__ = [
    "RED_LIVING_DEX_DEVELOPMENT_RUN_TERMINAL_SCHEMA",
    "RedLivingDexDevelopmentRunLedgerError",
    "RedLivingDexDevelopmentRunTerminal",
    "find_red_living_dex_development_run_terminal",
    "retain_red_living_dex_development_run_terminal",
]
