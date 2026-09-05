"""Repeatable loading of the exact five Red development inputs.

This module is deliberately pre-runtime and action-free.  It authenticates the
two surviving historical rows, all three supplement rows, and their owner-only
state/envelope pairs without constructing a ROM resolver or exposing paths.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from pokemon_red_completion.private_artifacts import PRIVATE_ROOT_SENTINEL, PrivateArtifactRoot
from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    RedLivingDexDevelopmentPlanBinding,
    load_red_living_dex_development_selection,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN,
)
from pokemon_red_completion.red_living_dex_development_batch import (
    RedLivingDexDevelopmentBatchAssignment,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (
    FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
)

RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS = (
    "historical-10",
    "historical-11",
    "supplement-0",
    "supplement-1",
    "supplement-2",
)

_MAXIMUM_STATE_BYTES = 16 * 1024 * 1024
_MAXIMUM_ENVELOPE_BYTES = 4 * 1024 * 1024
_CASES: dict[str, tuple[RedLivingDexDevelopmentPlanBinding, int]] = {
    "historical-10": (FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN, 10),
    "historical-11": (FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN, 11),
    "supplement-0": (FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT, 0),
    "supplement-1": (FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT, 1),
    "supplement-2": (FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT, 2),
}


class RedLivingDexDevelopmentInputError(RuntimeError):
    """One path-free input-authentication stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


def load_red_living_dex_development_batch_assignments(
    store: PrivateArtifactRoot,
    *,
    private_root: Path,
    roots: Mapping[str, Path],
) -> tuple[RedLivingDexDevelopmentBatchAssignment, ...]:
    """Read and join only the frozen five development state/envelope pairs."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("development input load needs its private store")
    if not isinstance(private_root, Path):
        raise TypeError("development input load needs its private root Path")
    if not isinstance(roots, Mapping) or set(roots) != set(_CASES):
        raise RedLivingDexDevelopmentInputError("arguments")
    assignments: list[RedLivingDexDevelopmentBatchAssignment] = []
    for label, (binding, ordinal) in _CASES.items():
        path = roots.get(label)
        if not isinstance(path, Path) or not path.is_absolute():
            raise RedLivingDexDevelopmentInputError("arguments")
        selection, _document = load_red_living_dex_development_selection(
            store,
            ordinal,
            binding=binding,
        )
        state_path = _private_regular(path, private_root=private_root)
        envelope_path = _private_regular(
            Path(f"{state_path}.json"),
            private_root=private_root,
        )
        try:
            root = RedLivingDexAuthenticatedSetupRoot(
                root_consumption_sha256=selection.logical_root_sha256,
                state_bytes=_read_private(
                    state_path,
                    maximum_bytes=_MAXIMUM_STATE_BYTES,
                ),
                envelope_bytes=_read_private(
                    envelope_path,
                    maximum_bytes=_MAXIMUM_ENVELOPE_BYTES,
                ),
            )
        except (TypeError, ValueError):
            raise RedLivingDexDevelopmentInputError(
                "selected_root_authentication"
            ) from None
        if (
            root.physical_root_sha256 != selection.physical_root_sha256
            or root.state_sha256 != selection.root_state_sha256
            or root.envelope_sha256 != selection.root_envelope_sha256
        ):
            raise RedLivingDexDevelopmentInputError(
                "selected_root_authentication"
            )
        assignments.append(
            RedLivingDexDevelopmentBatchAssignment(binding, ordinal, root)
        )
    return tuple(assignments)


def source_private_storage_is_separate(
    project_root: Path,
    private_root: Path,
) -> bool:
    """Return whether source and private roots occupy distinct devices."""

    if not isinstance(project_root, Path) or not isinstance(private_root, Path):
        raise TypeError("storage separation check needs Path inputs")
    try:
        project = project_root.resolve(strict=True)
        private = private_root.resolve(strict=True)
        return project.stat().st_dev != private.stat().st_dev
    except OSError:
        raise RedLivingDexDevelopmentInputError(
            "source_private_storage_separation"
        ) from None


def _private_regular(path: Path, *, private_root: Path) -> Path:
    try:
        root = private_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
        if (
            path.is_symlink()
            or resolved != path
            or not resolved.is_relative_to(root)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise OSError
        ancestor = resolved.parent
        while ancestor != root:
            if ancestor == ancestor.parent or not ancestor.is_relative_to(root):
                raise OSError
            if os.path.lexists(ancestor / PRIVATE_ROOT_SENTINEL):
                raise OSError
            ancestor = ancestor.parent
        return resolved
    except OSError:
        raise RedLivingDexDevelopmentInputError(
            "selected_root_authentication"
        ) from None


def _read_private(path: Path, *, maximum_bytes: int) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            named.st_dev != opened.st_dev
            or named.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) & 0o077
            or not 0 < opened.st_size <= maximum_bytes
        ):
            raise OSError
        payload = os.read(descriptor, opened.st_size + 1)
        finished = os.fstat(descriptor)
        if (
            len(payload) != opened.st_size
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise OSError
        return payload
    except OSError:
        raise RedLivingDexDevelopmentInputError(
            "selected_root_authentication"
        ) from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


__all__ = [
    "RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS",
    "RedLivingDexDevelopmentInputError",
    "load_red_living_dex_development_batch_assignments",
    "source_private_storage_is_separate",
]
