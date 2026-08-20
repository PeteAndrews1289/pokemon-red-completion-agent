"""Clean, reusable import bootstrap for future causal runners.

Import this module before any helper that imports ``pokemon_red_completion``, then
call :func:`load_causal_runner_modules`.  The development runner must establish the
reviewed source root and record an empty project-module inventory first.
"""

from __future__ import annotations

import importlib
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
_PROJECT_PACKAGE = "pokemon_red_completion"
_SAFE_STAGE = re.compile(r"[a-z0-9_]+\Z")

CAUSAL_RUNNER_BOOTSTRAP_DEPENDENCIES = (
    "bootstrap=scripts/causal_runner_bootstrap.py",
    "development_runner=scripts/run_repeatable_goal_manager_development.py",
    "multiroot_runner=scripts/run_resettable_goal_manager_multiroot_campaign.py",
    "paired_runner=scripts/run_paired_goal_manager_outcome_screen.py",
    "public_manifest=scripts/public_execution_manifest.py",
)

_READINESS_SUBSTAGES = {
    "source_authentication": "readiness_source_authentication",
    "external_executable_attestation": "readiness_executable_authentication",
    "executable_attestation": "readiness_executable_authentication",
    "import_origin_attestation": "readiness_executable_authentication",
    "development_runner_attestation": "readiness_executable_authentication",
    "external_context_plan_attestation": "readiness_context_plan_authentication",
    "context_plan_authentication": "readiness_context_plan_authentication",
    "prior_campaign_attestation": "readiness_prior_campaign_authentication",
    "prior_campaign_contract": "readiness_prior_campaign_authentication",
    "shadow_candidate_attestation": "readiness_candidate_authentication",
    "shadow_candidate_contract": "readiness_candidate_authentication",
}
_READINESS_ERROR_TYPES = frozenset(
    {
        "PairedScreenRunError",
        "RepeatableGoalManagerRunError",
        "ResettableMultirootRunError",
    }
)


class CausalRunnerBootstrapError(RuntimeError):
    """A path-free failure before future causal readiness may run."""

    def __init__(self, stage: str) -> None:
        safe = stage if _SAFE_STAGE.fullmatch(stage) is not None else "causal_bootstrap_internal"
        self.stage = safe
        super().__init__(safe)


@dataclass(frozen=True, slots=True)
class CausalRunnerModules:
    development: ModuleType
    paired: ModuleType
    multiroot: ModuleType
    public_manifest: ModuleType
    manifest_freezer: ModuleType


_CACHED: CausalRunnerModules | None = None


def load_causal_runner_modules() -> CausalRunnerModules:
    """Load the development runner first, then every causal helper it protects."""

    global _CACHED
    if _CACHED is not None:
        return _CACHED
    _prepend_scripts_root()
    preloaded = _project_modules()
    development_already_loaded = "run_repeatable_goal_manager_development" in sys.modules
    if preloaded and not development_already_loaded:
        raise CausalRunnerBootstrapError("causal_bootstrap_preloaded_project_modules")

    development = importlib.import_module("run_repeatable_goal_manager_development")
    _require_script_origin(development, "run_repeatable_goal_manager_development.py")
    recorded = getattr(development, "_PRELOADED_PROJECT_MODULES", None)
    require_origins = getattr(development, "_require_project_import_origins", None)
    if recorded != () or not callable(require_origins):
        raise CausalRunnerBootstrapError("causal_bootstrap_development_origin")
    try:
        require_origins()
    except Exception as error:
        raise CausalRunnerBootstrapError("causal_bootstrap_development_origin") from error

    public_manifest = importlib.import_module("public_execution_manifest")
    manifest_freezer = importlib.import_module("freeze_causal_execution_manifest")
    paired = importlib.import_module("run_paired_goal_manager_outcome_screen")
    multiroot = importlib.import_module("run_resettable_goal_manager_multiroot_campaign")
    for module, filename in (
        (public_manifest, "public_execution_manifest.py"),
        (manifest_freezer, "freeze_causal_execution_manifest.py"),
        (paired, "run_paired_goal_manager_outcome_screen.py"),
        (multiroot, "run_resettable_goal_manager_multiroot_campaign.py"),
    ):
        _require_script_origin(module, filename)
    _CACHED = CausalRunnerModules(
        development=development,
        paired=paired,
        multiroot=multiroot,
        public_manifest=public_manifest,
        manifest_freezer=manifest_freezer,
    )
    return _CACHED


def sanitized_readiness_substage(error: BaseException) -> str:
    """Map reviewed readiness failures to narrow path-free future-runner stages."""

    if type(error).__name__ not in _READINESS_ERROR_TYPES:
        return "readiness_internal"
    raw = getattr(error, "stage", None)
    if raw is None and len(error.args) == 1:
        raw = error.args[0]
    if not isinstance(raw, str) or _SAFE_STAGE.fullmatch(raw) is None:
        return "readiness_internal"
    return _READINESS_SUBSTAGES.get(raw, "readiness_internal")


def _prepend_scripts_root() -> None:
    while str(SCRIPTS_ROOT) in sys.path:
        sys.path.remove(str(SCRIPTS_ROOT))
    sys.path.insert(0, str(SCRIPTS_ROOT))


def _project_modules() -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name in sys.modules
            if name == _PROJECT_PACKAGE or name.startswith(f"{_PROJECT_PACKAGE}.")
        )
    )


def _require_script_origin(module: ModuleType, filename: str) -> None:
    raw = getattr(module, "__file__", None)
    expected = SCRIPTS_ROOT / filename
    if not isinstance(raw, str):
        raise CausalRunnerBootstrapError("causal_bootstrap_script_origin")
    path = Path(raw)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
        expected_resolved = expected.resolve(strict=True)
    except OSError:
        raise CausalRunnerBootstrapError("causal_bootstrap_script_origin") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or resolved != expected_resolved
    ):
        raise CausalRunnerBootstrapError("causal_bootstrap_script_origin")
