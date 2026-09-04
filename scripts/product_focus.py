"""Machine-checked product focus for the cross-game Pokemon agent.

The JSON contract is the single editable source.  ``ACTIVE_PRODUCT_STATE.md`` and the
view-only focus dashboard are projections of it.  Keeping parsing, validation and rendering in
one small ROM-free module makes a stale or weakened focus declaration fail CI instead of becoming
another contradictory handoff section.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOCUS_CONFIG = PROJECT_ROOT / "configs" / "active-product-focus.json"
DEFAULT_FOCUS_DOCUMENT = PROJECT_ROOT / "ACTIVE_PRODUCT_STATE.md"
FOCUS_SCHEMA = "pokemon.product-focus.v4"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_LANE_KINDS = {"learning", "maintenance"}
_RIGOR_TIERS = {"development", "benchmark", "sealed"}
_OUTPUT_KINDS = {
    "atomic_goal_episode",
    "authority_promotion",
    "causal_train_example",
    "composition_attempt",
    "development_episode",
    "model_fit",
    "outcome_question",
    "synthetic_rootless_atomic_goal_episode",
    "synthetic_rootless_model_fit",
    "synthetic_rootless_train_outcome",
    "synthetic_rootless_unseen_comparison",
    "transfer_result",
    "unseen_comparison",
    "verified_composition_episode",
    "verified_outcome_example",
}
_REORIENTATION_EVIDENCE_KINDS = _OUTPUT_KINDS | {"falsification", "qualification"}
_OUTPUT_PARTITIONS = {"development", "none", "train", "transfer"}
_REQUIRED_DEVELOPMENT_PROHIBITIONS = {
    "cloned_or_rehashed_root_independence",
    "consumed_trial_retry",
    "crystal_execution",
    "full_game_replay",
    "model_fit_on_development",
    "routine_clean_power_teacher_factory",
    "sealed_red_evaluation",
    "teacher_choice_or_fallback",
    "teacher_route_hardening",
    "unexecuted_counterfactual_target",
    "unmeasured_action_target",
}
_REQUIRED_STATUS_FIELDS = {
    "active_lane",
    "authority_delta",
    "blocker",
    "current_counters",
    "learning_output",
    "next_decision",
    "product_goal",
    "stop_condition",
    "time_box",
    "transfer_result",
}
_PROJECTED_COUNTER_PREFIX_EVIDENCE_SHA256 = (
    "c2d45a4dcf544325792ca704069b2ab2b675235661de730b5b67e5bae86ac7a0"
)
_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT = 17
_BATTLE_CYCLE_RESULT_PATH = (
    "docs/evidence/red-battle-outcome-cycle-v1-pair-01-result-2026-08-31.json"
)
_BATTLE_CYCLE_RESULT_SHA256 = (
    "8533368231a3ba6273e848ae65757e0dc1e48a02356488aa2cdeb6413d732ec7"
)
_REPEATABLE_BATTLE_RESULT_PATH = (
    "docs/evidence/repeatable-red-battle-learning-loop-v1-2026-09-02.json"
)
_REPEATABLE_BATTLE_RESULT_SHA256 = (
    "4954739e28512c2fabcc702d90fb65cdc2e45662a5647edf98f82e9f66f265c5"
)
_FIRST_AUTHENTIC_BATTLE_RESULT_PATH = (
    "docs/evidence/red-repeatable-battle-first-authentic-result-2026-09-03.json"
)
_FIRST_AUTHENTIC_BATTLE_RESULT_SHA256 = (
    "6f010cc6510e7ef7a0e37579a757df7de49b47350dd1ee7ea83f1b4e253c017d"
)
_EXPECTED_UTILITY_BATTLE_RESULT_PATH = (
    "docs/evidence/red-repeatable-battle-expected-utility-result-2026-09-03.json"
)
_EXPECTED_UTILITY_BATTLE_RESULT_SHA256 = (
    "7ba351061a36c6a622521bed70a9b5a1cba69b271d28d07e0a059ece6d9fc551"
)
_PAIRED_BOUNDED_PLAYER_RESULT_PATH = (
    "docs/evidence/red-paired-bounded-player-result-2026-09-03.json"
)
_PAIRED_BOUNDED_PLAYER_RESULT_SHA256 = (
    "ac9987ef212083ac6510849bc2a7a8faae0734db9a7a18d1931ac63f2500ada1"
)
_CAUSAL_PLAYER_RESULT_PATH = (
    "docs/evidence/red-causal-player-pair-003-result-2026-09-03.json"
)
_CAUSAL_PLAYER_RESULT_SHA256 = (
    "4b4466756b33bc0a41fc711e608f992a8f0a43fc80360c01f6a5685bf0683bbb"
)
_MULTI_GOAL_CALIBRATION_PROGRESS_PATH = (
    "docs/evidence/red-multi-goal-calibration-progress-2026-09-03.json"
)
_MULTI_GOAL_CALIBRATION_PROGRESS_SHA256 = (
    "22eebf59f1b82f17f95f54328714cfee2a70dcc8ee11d3f2df3a731568497473"
)
_CALIBRATION_PLAYER_RESULT_PATH = (
    "docs/evidence/red-calibration-player-pair-004-result-2026-09-04.json"
)
_CALIBRATION_PLAYER_RESULT_SHA256 = (
    "3602457d8ca03b5e2df817285cf72d1bc3180ab08844dcfeee4dae8238e60b40"
)
_CALIBRATION_PLAYER_PARTIAL_RESULT_PATH = (
    "docs/evidence/red-calibration-player-pair-005-partial-result-2026-09-04.json"
)
_CALIBRATION_PLAYER_PARTIAL_RESULT_SHA256 = (
    "aebd493ee22397c8833ec2894c6ede0eabe15dac093f9c2edbfae395eb7c0d74"
)
_PROJECTED_COUNTERS = {
    "atomic_goal_episodes": 0,
    "authority_promotions": 0,
    "causal_train_examples": 111,
    "composition_attempts": 5,
    "development_episode_attempts": 22,
    "model_fits": 10,
    "outcome_questions": {"development": 56, "train": 103},
    "synthetic_rootless_atomic_goal_episodes": 8,
    "synthetic_rootless_model_fits": 1,
    "synthetic_rootless_train_outcomes": 8,
    "synthetic_rootless_unseen_comparisons": 1,
    "transfer_results": 0,
    "unseen_comparisons": 9,
    "verified_composition_episodes": 3,
    "verified_outcome_examples": 61,
}


class ProductFocusError(ValueError):
    """Raised when the active product contract is missing, stale or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class ProductFocusState:
    """Validated focus state with the one active lane selected."""

    document: Mapping[str, object]
    active_lane: Mapping[str, object]
    retired_lanes: tuple[Mapping[str, object], ...]

    @property
    def product(self) -> Mapping[str, object]:
        return _mapping(self.document, "product", subject="product focus")

    @property
    def progress(self) -> Mapping[str, object]:
        return _mapping(self.active_lane, "progress", subject="active lane")

    @property
    def measurable_outputs(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            _mapping_value(value, subject="measurable output")
            for value in _sequence(
                self.active_lane,
                "measurable_outputs",
                subject="active lane",
            )
        )


def canonical_focus_json(document: Mapping[str, object]) -> bytes:
    """Return the review-friendly canonical bytes required for the tracked contract."""

    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def load_product_focus(
    path: Path = DEFAULT_FOCUS_CONFIG,
    *,
    project_root: Path = PROJECT_ROOT,
) -> ProductFocusState:
    """Load canonical unique-key JSON and validate every focus invariant."""

    try:
        payload = path.read_bytes()
    except OSError:
        raise ProductFocusError("active product focus config is unavailable") from None
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("active product focus config is invalid JSON") from None
    if not isinstance(value, dict):
        raise ProductFocusError("active product focus config must be an object")
    if payload != canonical_focus_json(value):
        raise ProductFocusError("active product focus config is not canonical JSON")
    return validate_product_focus_document(value, project_root=project_root)


def validate_product_focus_document(
    document: Mapping[str, object],
    *,
    project_root: Path | None = None,
) -> ProductFocusState:
    """Validate product, lane, rigor, budget, alarm, evidence and reporting contracts."""

    _require_keys(
        document,
        {
            "alarms",
            "lanes",
            "product",
            "review_roles",
            "rigor_policy",
            "schema",
            "session_budget_percent",
            "status_report",
        },
        subject="product focus",
    )
    if document.get("schema") != FOCUS_SCHEMA:
        raise ProductFocusError("active product focus schema is unsupported")
    _validate_product(_mapping(document, "product", subject="product focus"))

    lanes = tuple(
        _mapping_value(value, subject="focus lane")
        for value in _sequence(document, "lanes", subject="product focus")
    )
    if not lanes:
        raise ProductFocusError("product focus must declare at least one lane")
    lane_ids: set[str] = set()
    active: list[Mapping[str, object]] = []
    retired: list[Mapping[str, object]] = []
    for lane in lanes:
        lane_id = _identifier(lane, "id", subject="focus lane")
        if lane_id in lane_ids:
            raise ProductFocusError("focus lane identifiers must be unique")
        lane_ids.add(lane_id)
        status = _text(lane, "status", subject="focus lane")
        if status == "active":
            _validate_active_lane(lane)
            active.append(lane)
        elif status == "retired":
            _validate_retired_lane(lane)
            retired.append(lane)
        else:
            raise ProductFocusError("focus lane status must be active or retired")
    if len(active) != 1:
        raise ProductFocusError("product focus must contain exactly one active lane")

    _validate_rigor_policy(_mapping(document, "rigor_policy", subject="product focus"))
    _validate_session_budget(_mapping(document, "session_budget_percent", subject="product focus"))
    _validate_alarms(_mapping(document, "alarms", subject="product focus"))
    _validate_status_report(_mapping(document, "status_report", subject="product focus"))
    _validate_review_roles(_mapping(document, "review_roles", subject="product focus"))
    _validate_progress_evidence(active[0], project_root=project_root)
    _validate_projected_counters(active[0], project_root=project_root)
    return ProductFocusState(document, active[0], tuple(retired))


def focus_progress_fraction(state: ProductFocusState) -> float:
    """Return the mean capped completion fraction across declared learning outputs."""

    progress = state.progress
    fractions: list[float] = []
    for output in state.measurable_outputs:
        minimum = _positive_int(output, "minimum", subject="measurable output")
        current = _current_output_count(progress, output)
        fractions.append(min(current / minimum, 1.0))
    return sum(fractions) / len(fractions) if fractions else 0.0


def focus_scorecard(state: ProductFocusState) -> tuple[tuple[str, int, int], ...]:
    """Return human-readable current/minimum rows in their declared order."""

    rows: list[tuple[str, int, int]] = []
    for output in state.measurable_outputs:
        kind = _text(output, "kind", subject="measurable output")
        partition = _text(output, "partition", subject="measurable output")
        minimum = _positive_int(output, "minimum", subject="measurable output")
        label = kind.replace("_", " ").title()
        if partition != "none":
            label = f"{label} · {partition}"
        rows.append((label, _current_output_count(state.progress, output), minimum))
    return tuple(rows)


def render_product_focus_markdown(state: ProductFocusState) -> str:
    """Render the one-page human source of current product truth."""

    product = state.product
    lane = state.active_lane
    authority = _mapping(lane, "learned_authority", subject="active lane")
    time_box = _mapping(lane, "time_box", subject="active lane")
    time_box_sessions = _positive_int(time_box, "maximum_sessions", subject="time box")
    time_box_session_label = "session" if time_box_sessions == 1 else "sessions"
    time_box_hours = _positive_int(time_box, "maximum_hours", subject="time box")
    time_box_hour_label = "hour" if time_box_hours == 1 else "hours"
    progress = state.progress
    reorientation = _mapping(
        lane,
        "latest_reorientation",
        subject="active lane",
    )
    reorientation_evidence = _mapping(
        reorientation,
        "evidence",
        subject="latest reorientation",
    )
    reorientation_evidence_kind = _text(
        reorientation_evidence,
        "kind",
        subject="reorientation evidence",
    ).replace("_", " ")
    reorientation_evidence_path = _text(
        reorientation_evidence,
        "path",
        subject="reorientation evidence",
    )
    budgets = _mapping(
        state.document,
        "session_budget_percent",
        subject="product focus",
    )
    alarms = _mapping(state.document, "alarms", subject="product focus")
    rigor = _mapping(state.document, "rigor_policy", subject="product focus")
    roles = _mapping(state.document, "review_roles", subject="product focus")
    status = _mapping(state.document, "status_report", subject="product focus")
    data_budget = _count(budgets, "data_and_scenarios", subject="session budget")
    model_budget = _count(budgets, "model_and_evaluation", subject="session budget")
    maintenance_budget = _count(budgets, "maintenance_and_docs", subject="session budget")
    session_alarm = _count(
        alarms,
        "maximum_sessions_without_measured_learning_output",
        subject="alarms",
    )
    ci_alarm = _count(alarms, "maximum_consecutive_ci_only_repairs", subject="alarms")
    lines = [
        "<!-- Generated from configs/active-product-focus.json by scripts/product_focus.py. -->",
        "<!-- Edit the JSON source, then run scripts/check_product_focus.py. -->",
        "# Active product state",
        "",
        "This is the compact answer to **what are we building, what are we doing now, and what",
        (
            "evidence must exist before we move on?** It is subordinate only to "
            "[MISSION.md](MISSION.md)"
        ),
        "and [NORTH_STAR.md](NORTH_STAR.md). Older roadmap and handoff sections are history when",
        "they conflict with this page.",
        "",
        "## Product",
        "",
        _text(product, "goal", subject="product"),
        "",
        f"**Environment role:** {_text(product, 'environment_role', subject='product')}",
        "",
        "Success means:",
        "",
    ]
    lines.extend(
        f"- {item}" for item in _text_sequence(product, "success_conditions", subject="product")
    )
    lines.extend(
        [
            "",
            "Not the product:",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in _text_sequence(product, "non_goals", subject="product"))
    lines.extend(
        [
            "",
            "## One active lane",
            "",
            f"**{_text(lane, 'name', subject='active lane')}** "
            f"(`{_identifier(lane, 'id', subject='active lane')}`)",
            "",
            f"- Kind: **{_text(lane, 'kind', subject='active lane')}**",
            f"- Rigor: **{_text(lane, 'rigor', subject='active lane')}**",
            f"- Next decision: {_text(lane, 'next_decision', subject='active lane')}",
            "",
            "### Mandatory mission check",
            "",
            "| Question | Current answer |",
            "| --- | --- |",
            _table_row("Reusable capability", _text(lane, "capability", subject="active lane")),
            _table_row(
                "Authority now",
                _text(authority, "current", subject="learned authority"),
            ),
            _table_row(
                "Authority target",
                _text(authority, "target", subject="learned authority"),
            ),
            _table_row("Transfer test", _text(lane, "transfer_test", subject="active lane")),
            _table_row(
                "Cheapest falsifier",
                _text(lane, "cheapest_falsifier", subject="active lane"),
            ),
            (
                f"| Time box | {time_box_sessions} {time_box_session_label} / "
                f"{time_box_hours} {time_box_hour_label} |"
            ),
            "",
            "### Cumulative cross-family learning outputs",
            "",
            "| Output | Current | Minimum for the next decision |",
            "| --- | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {label} | {current} | {minimum} |" for label, current, minimum in focus_scorecard(state)
    )
    lines.extend(
        [
            "",
            "Each counter changes only when tracked, path-free evidence supports it.",
            (
                "These totals aggregate several learner heads and historical scenario families; "
                "they do not by themselves gate battle-model promotion."
            ),
            (
                "Infrastructure, preflights, teacher runs, CI passes, and frozen inputs are not "
                "learning"
            ),
            "outputs.",
            "",
            "### Latest session reorientation",
            "",
            (
                f"**{_text(reorientation, 'session_id', subject='latest reorientation')}** · "
                f"status **{_text(reorientation, 'status', subject='latest reorientation')}** · "
                f"evidence [{reorientation_evidence_kind}]({reorientation_evidence_path})"
            ),
            "",
            "| Check | Session conclusion |",
            "| --- | --- |",
            _table_row(
                "Product alignment",
                _text(reorientation, "product_alignment", subject="latest reorientation"),
            ),
            _table_row(
                "Learning output",
                _text(reorientation, "learning_output", subject="latest reorientation"),
            ),
            _table_row(
                "Authority delta",
                _text(reorientation, "authority_delta", subject="latest reorientation"),
            ),
            _table_row(
                "Transfer result",
                _text(reorientation, "transfer_result", subject="latest reorientation"),
            ),
            _table_row(
                "Blocker",
                _text(reorientation, "blocker", subject="latest reorientation"),
            ),
            _table_row(
                "Decision",
                _text(reorientation, "decision", subject="latest reorientation"),
            ),
            _table_row(
                "Next session",
                _text(reorientation, "next_session_goal", subject="latest reorientation"),
            ),
            _table_row(
                "Next falsifier",
                _text(reorientation, "next_falsifier", subject="latest reorientation"),
            ),
            _table_row(
                "Stop condition",
                _text(reorientation, "stop_condition", subject="latest reorientation"),
            ),
            "",
            "### Stop conditions",
            "",
        ]
    )
    lines.extend(
        f"- {item}" for item in _text_sequence(lane, "stop_conditions", subject="active lane")
    )
    lines.extend(
        [
            "",
            "### Hard boundaries for this lane",
            "",
        ]
    )
    lines.extend(
        f"- **Prohibited:** {item.replace('_', ' ')}"
        for item in _text_sequence(lane, "prohibited_actions", subject="active lane")
    )
    lines.extend(
        [
            "",
            "## Rigor belongs to the risk",
            "",
            (
                "| Tier | Repeatable | Per-case owner authorization | Exact source/CI binding | "
                "External review |"
            ),
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for tier in ("development", "benchmark", "sealed"):
        policy = _mapping(rigor, tier, subject="rigor policy")
        lines.append(
            "| "
            f"{tier.title()} | {_yes_no(_bool(policy, 'repeatable', subject=tier))} | "
            f"{_yes_no(_bool(policy, 'owner_authorization_per_case', subject=tier))} | "
            f"{_yes_no(_bool(policy, 'exact_source_ci_binding', subject=tier))} | "
            f"{_text(policy, 'external_review', subject=tier).replace('_', ' ')} |"
        )
    lines.extend(
        [
            "",
            "Development is the fast learning loop. Benchmark and sealed rigor are reserved for",
            "claims that justify their cost; they must not be copied into routine data generation.",
            "",
            "## Session allocation and alarms",
            "",
            f"- **{data_budget}%** data and scenarios",
            f"- **{model_budget}%** model and evaluation",
            f"- **{maintenance_budget}%** maintenance and documentation",
            "",
            (
                "Stop and reassess after **"
                f"{session_alarm}"
                "** session without a measured learning output, after **"
                f"{ci_alarm}** consecutive CI-only repair, or before any full replay. Repeated "
                "fixed-route patches"
            ),
            "and unmeasured teacher-label copying are also hard alarms.",
            "",
            "## Reviewer use",
            "",
            f"- **Codex:** {_text(roles, 'codex', subject='review roles')}",
            f"- **Claude:** {_text(roles, 'claude', subject='review roles')}",
            f"- **Antigravity:** {_text(roles, 'antigravity', subject='review roles')}",
            "",
            "## Retired leading edges",
            "",
        ]
    )
    for retired in state.retired_lanes:
        lines.append(
            f"- **{_text(retired, 'name', subject='retired lane')}:** "
            f"{_text(retired, 'reason', subject='retired lane')} Evidence is preserved; retry is "
            f"{_yes_no(_bool(retired, 'retry_allowed', subject='retired lane')).lower()}."
        )
    lines.extend(
        [
            "",
            "## Required status report",
            "",
            f"Counter source: {_text(status, 'counter_source', subject='status report')}",
            "",
            "Every meaningful update reports:",
            "",
        ]
    )
    lines.extend(
        f"- {field.replace('_', ' ')}"
        for field in _text_sequence(status, "required_fields", subject="status report")
    )
    evidence = _sequence(progress, "evidence", subject="active lane progress")
    lines.extend(
        [
            "",
            f"Current evidence entries: **{len(evidence)}**.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_product(product: Mapping[str, object]) -> None:
    _require_keys(
        product,
        {"environment_role", "goal", "non_goals", "success_conditions"},
        subject="product",
    )
    goal = _text(product, "goal", subject="product")
    lowered = goal.lower()
    if "living pokedex" not in lowered or "mainline games" not in lowered:
        raise ProductFocusError("product goal must retain the cross-game living Pokedex objective")
    if len(_text_sequence(product, "success_conditions", subject="product")) < 3:
        raise ProductFocusError("product success conditions are incomplete")
    if len(_text_sequence(product, "non_goals", subject="product")) < 3:
        raise ProductFocusError("product non-goals are incomplete")
    _text(product, "environment_role", subject="product")


def _validate_active_lane(lane: Mapping[str, object]) -> None:
    _require_keys(
        lane,
        {
            "capability",
            "cheapest_falsifier",
            "id",
            "kind",
            "latest_reorientation",
            "learned_authority",
            "maintenance_unblocks",
            "measurable_outputs",
            "name",
            "next_decision",
            "prohibited_actions",
            "progress",
            "rigor",
            "status",
            "stop_conditions",
            "time_box",
            "transfer_test",
        },
        subject="active lane",
    )
    kind = _text(lane, "kind", subject="active lane")
    if kind not in _LANE_KINDS:
        raise ProductFocusError("active lane kind is unsupported")
    rigor = _text(lane, "rigor", subject="active lane")
    if rigor not in _RIGOR_TIERS:
        raise ProductFocusError("active lane rigor tier is unsupported")
    for key in (
        "capability",
        "cheapest_falsifier",
        "name",
        "next_decision",
        "transfer_test",
    ):
        _text(lane, key, subject="active lane")
    authority = _mapping(lane, "learned_authority", subject="active lane")
    _require_keys(authority, {"current", "target"}, subject="learned authority")
    _text(authority, "current", subject="learned authority")
    _text(authority, "target", subject="learned authority")
    time_box = _mapping(lane, "time_box", subject="active lane")
    _require_keys(time_box, {"maximum_hours", "maximum_sessions"}, subject="time box")
    if _positive_int(time_box, "maximum_sessions", subject="time box") > 3:
        raise ProductFocusError("active lane time box exceeds three sessions")
    _positive_int(time_box, "maximum_hours", subject="time box")
    if len(_text_sequence(lane, "stop_conditions", subject="active lane")) < 2:
        raise ProductFocusError("active lane must declare at least two stop conditions")

    unblocks = lane.get("maintenance_unblocks")
    outputs = tuple(
        _mapping_value(value, subject="measurable output")
        for value in _sequence(lane, "measurable_outputs", subject="active lane")
    )
    if kind == "learning":
        if unblocks is not None:
            raise ProductFocusError("learning lane cannot declare a maintenance unblock")
        _validate_learning_outputs(outputs)
    else:
        if not isinstance(unblocks, str) or _IDENTIFIER.fullmatch(unblocks) is None:
            raise ProductFocusError("maintenance lane must name the learning lane it unblocks")
        if outputs:
            raise ProductFocusError("maintenance lane cannot claim learning outputs")

    prohibited = set(_text_sequence(lane, "prohibited_actions", subject="active lane"))
    if rigor == "development" and not prohibited >= _REQUIRED_DEVELOPMENT_PROHIBITIONS:
        raise ProductFocusError("development lane is missing a protected-action prohibition")
    _validate_forward_plan(lane, prohibited=prohibited)
    progress = _mapping(lane, "progress", subject="active lane")
    _validate_progress(progress)
    _validate_latest_reorientation(
        _mapping(lane, "latest_reorientation", subject="active lane"),
    )


def _validate_forward_plan(
    lane: Mapping[str, object],
    *,
    prohibited: set[str],
) -> None:
    """Keep an active decision from scheduling the action it already prohibits."""

    reorientation = _mapping(lane, "latest_reorientation", subject="active lane")
    forward_text = " ".join(
        (
            _text(lane, "cheapest_falsifier", subject="active lane"),
            _text(lane, "next_decision", subject="active lane"),
            _text(reorientation, "decision", subject="latest reorientation"),
            _text(reorientation, "next_falsifier", subject="latest reorientation"),
            _text(reorientation, "next_session_goal", subject="latest reorientation"),
        )
    ).lower()
    if "teacher_route_hardening" in prohibited and any(
        phrase in forward_text
        for phrase in (
            "clean-power factory",
            "clean power factory",
            "full-game teacher",
            "full game teacher",
            "teacher-route hardening",
            "teacher route hardening",
        )
    ):
        raise ProductFocusError(
            "active forward plan schedules prohibited teacher-route maintenance"
        )
    if "full_game_replay" in prohibited and any(
        phrase in forward_text
        for phrase in ("full-game replay", "full game replay", "full red replay")
    ):
        raise ProductFocusError(
            "active forward plan schedules a prohibited full-game replay"
        )


def _validate_retired_lane(lane: Mapping[str, object]) -> None:
    _require_keys(
        lane,
        {
            "id",
            "kind",
            "name",
            "preserve_evidence",
            "reason",
            "retry_allowed",
            "rigor",
            "status",
        },
        subject="retired lane",
    )
    if _text(lane, "kind", subject="retired lane") not in _LANE_KINDS:
        raise ProductFocusError("retired lane kind is unsupported")
    if _text(lane, "rigor", subject="retired lane") not in _RIGOR_TIERS:
        raise ProductFocusError("retired lane rigor is unsupported")
    _text(lane, "name", subject="retired lane")
    _text(lane, "reason", subject="retired lane")
    if not _bool(lane, "preserve_evidence", subject="retired lane"):
        raise ProductFocusError("retired lane evidence must remain preserved")
    if _bool(lane, "retry_allowed", subject="retired lane"):
        raise ProductFocusError("retired consumed lane cannot allow retry")


def _validate_learning_outputs(outputs: Sequence[Mapping[str, object]]) -> None:
    if not outputs:
        raise ProductFocusError("learning lane must declare measurable outputs")
    identities: set[tuple[str, str]] = set()
    kinds: set[str] = set()
    minima: dict[str, int] = {}
    for output in outputs:
        _require_keys(output, {"kind", "minimum", "partition"}, subject="measurable output")
        kind = _text(output, "kind", subject="measurable output")
        partition = _text(output, "partition", subject="measurable output")
        if kind not in _OUTPUT_KINDS or partition not in _OUTPUT_PARTITIONS:
            raise ProductFocusError("measurable output kind or partition is unsupported")
        if (
            kind
            in {
                "atomic_goal_episode",
                "composition_attempt",
                "development_episode",
                "verified_composition_episode",
                "verified_outcome_example",
            }
            and partition != "development"
        ):
            raise ProductFocusError(
                "model-led development output must use the development partition"
            )
        if kind == "causal_train_example" and partition != "train":
            raise ProductFocusError("causal train example must use the train partition")
        if (
            kind
            in {
                "synthetic_rootless_atomic_goal_episode",
                "synthetic_rootless_model_fit",
                "synthetic_rootless_train_outcome",
            }
            and partition != "train"
        ):
            raise ProductFocusError("synthetic rootless output must use the train partition")
        if kind == "synthetic_rootless_unseen_comparison" and partition != "development":
            raise ProductFocusError(
                "synthetic rootless unseen comparison must use the development partition"
            )
        identity = (kind, partition)
        if identity in identities:
            raise ProductFocusError("measurable output identities must be unique")
        identities.add(identity)
        kinds.add(kind)
        minima[kind] = _positive_int(output, "minimum", subject="measurable output")
    legacy_contract = {"outcome_question", "model_fit", "unseen_comparison"} <= kinds
    development_contract = {
        "development_episode",
        "verified_outcome_example",
    } <= kinds
    composition_contract = {
        "composition_attempt",
        "development_episode",
        "verified_composition_episode",
    } <= kinds
    causal_train_contract = "causal_train_example" in kinds
    synthetic_rootless_contract = {
        "synthetic_rootless_atomic_goal_episode",
        "synthetic_rootless_train_outcome",
    } <= kinds
    synthetic_rootless_fit_contract = "synthetic_rootless_model_fit" in kinds
    synthetic_rootless_comparison_contract = "synthetic_rootless_unseen_comparison" in kinds
    if synthetic_rootless_contract and (
        minima["synthetic_rootless_atomic_goal_episode"]
        != minima["synthetic_rootless_train_outcome"]
    ):
        raise ProductFocusError("synthetic rootless output minima must match")
    if (
            not legacy_contract
            and not development_contract
            and not composition_contract
            and not causal_train_contract
        and not (synthetic_rootless_contract)
        and not synthetic_rootless_fit_contract
        and not synthetic_rootless_comparison_contract
    ):
        raise ProductFocusError(
                "learning lane must require either the legacy fit/evaluation outputs or "
                "model-led development episodes with verified outcomes, a causal train example, "
                "verified composition outputs, paired synthetic rootless outputs, a synthetic "
                "rootless fit, or a synthetic rootless comparison"
            )


def _validate_progress(progress: Mapping[str, object]) -> None:
    _require_keys(
        progress,
        {
            "authority_promotions",
            "atomic_goal_episodes",
            "causal_train_examples",
            "composition_attempts",
            "development_episode_attempts",
            "evidence",
            "model_fits",
            "outcome_questions",
            "synthetic_rootless_atomic_goal_episodes",
            "synthetic_rootless_model_fits",
            "synthetic_rootless_train_outcomes",
            "synthetic_rootless_unseen_comparisons",
            "transfer_results",
            "unseen_comparisons",
            "verified_composition_episodes",
            "verified_outcome_examples",
        },
        subject="active lane progress",
    )
    outcomes = _mapping(progress, "outcome_questions", subject="active lane progress")
    _require_keys(outcomes, {"development", "train"}, subject="outcome progress")
    _count(outcomes, "train", subject="outcome progress")
    _count(outcomes, "development", subject="outcome progress")
    for key in (
        "authority_promotions",
        "atomic_goal_episodes",
        "causal_train_examples",
        "composition_attempts",
        "development_episode_attempts",
        "model_fits",
        "synthetic_rootless_atomic_goal_episodes",
        "synthetic_rootless_model_fits",
        "synthetic_rootless_train_outcomes",
        "synthetic_rootless_unseen_comparisons",
        "transfer_results",
        "unseen_comparisons",
        "verified_composition_episodes",
        "verified_outcome_examples",
    ):
        _count(progress, key, subject="active lane progress")
    evidence = _sequence(progress, "evidence", subject="active lane progress")
    seen_paths: set[str] = set()
    for raw in evidence:
        item = _mapping_value(raw, subject="progress evidence")
        _require_keys(item, {"kind", "path", "sha256"}, subject="progress evidence")
        kind = _text(item, "kind", subject="progress evidence")
        if kind not in _OUTPUT_KINDS:
            raise ProductFocusError("progress evidence kind is unsupported")
        path = _text(item, "path", subject="progress evidence")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or path in seen_paths:
            raise ProductFocusError("progress evidence path is unsafe or duplicated")
        seen_paths.add(path)
        digest = _text(item, "sha256", subject="progress evidence")
        if _SHA256.fullmatch(digest) is None:
            raise ProductFocusError("progress evidence SHA-256 is invalid")


def _validate_latest_reorientation(
    reorientation: Mapping[str, object],
) -> None:
    _require_keys(
        reorientation,
        {
            "authority_delta",
            "blocker",
            "decision",
            "evidence",
            "learning_output",
            "next_falsifier",
            "next_session_goal",
            "product_alignment",
            "session_id",
            "status",
            "stop_condition",
            "transfer_result",
        },
        subject="latest reorientation",
    )
    _identifier(reorientation, "session_id", subject="latest reorientation")
    if _text(reorientation, "status", subject="latest reorientation") not in {
        "active",
        "closed",
    }:
        raise ProductFocusError("latest reorientation status is unsupported")
    for key in (
        "authority_delta",
        "blocker",
        "decision",
        "learning_output",
        "next_falsifier",
        "next_session_goal",
        "product_alignment",
        "stop_condition",
        "transfer_result",
    ):
        _text(reorientation, key, subject="latest reorientation")
    evidence = _mapping(reorientation, "evidence", subject="latest reorientation")
    _require_keys(evidence, {"kind", "path", "sha256"}, subject="reorientation evidence")
    kind = _text(evidence, "kind", subject="reorientation evidence")
    if kind not in _REORIENTATION_EVIDENCE_KINDS:
        raise ProductFocusError("reorientation evidence kind is unsupported")
    path = _text(evidence, "path", subject="reorientation evidence")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise ProductFocusError("reorientation evidence path is unsafe")
    digest = _text(evidence, "sha256", subject="reorientation evidence")
    if _SHA256.fullmatch(digest) is None:
        raise ProductFocusError("reorientation evidence SHA-256 is invalid")


def _validate_progress_evidence(
    lane: Mapping[str, object],
    *,
    project_root: Path | None,
) -> None:
    progress = _mapping(lane, "progress", subject="active lane")
    counts = _current_progress_counts(progress)
    evidence = tuple(
        _mapping_value(value, subject="progress evidence")
        for value in _sequence(progress, "evidence", subject="active lane progress")
    )
    if any(counts) and not evidence:
        raise ProductFocusError("nonzero learning progress requires tracked evidence")
    if not any(counts) and evidence:
        raise ProductFocusError("zero learning progress cannot cite advancement evidence")
    if project_root is None:
        return
    root = project_root.resolve()
    reorientation = _mapping(lane, "latest_reorientation", subject="active lane")
    reorientation_evidence = _mapping(
        reorientation,
        "evidence",
        subject="latest reorientation",
    )
    evidence_to_check = tuple((item, "progress evidence") for item in evidence) + (
        (reorientation_evidence, "reorientation evidence"),
    )
    for item, subject in evidence_to_check:
        relative = _text(item, "path", subject=subject)
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ProductFocusError(f"{subject} file is unavailable")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != _text(item, "sha256", subject=subject):
            raise ProductFocusError(f"{subject} file digest differs")


def _validate_projected_counters(
    lane: Mapping[str, object],
    *,
    project_root: Path | None,
) -> None:
    """Prevent the live board from out-running its typed evidence projection.

    The current lane begins from a frozen, already-audited evidence prefix.  A
    new receipt schema must gain an explicit projection here before either the
    prefix or any counter can advance.  That deliberate code gate prevents a
    manual JSON edit from turning infrastructure work into apparent learning.
    """

    progress = _mapping(lane, "progress", subject="active lane")
    evidence = _sequence(progress, "evidence", subject="active lane progress")
    if len(evidence) != _PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT + 9:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    prefix_payload = json.dumps(
        evidence[:_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT],
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    if (
        hashlib.sha256(prefix_payload).hexdigest()
        != _PROJECTED_COUNTER_PREFIX_EVIDENCE_SHA256
    ):
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    battle_cycle_evidence = _mapping_value(
        evidence[_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT],
        subject="projected battle-cycle evidence",
    )
    if battle_cycle_evidence != {
        "kind": "causal_train_example",
        "path": _BATTLE_CYCLE_RESULT_PATH,
        "sha256": _BATTLE_CYCLE_RESULT_SHA256,
    }:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    root = (project_root or PROJECT_ROOT).resolve()
    receipt_path = (root / _BATTLE_CYCLE_RESULT_PATH).resolve()
    if not receipt_path.is_relative_to(root):  # pragma: no cover - constant path
        raise ProductFocusError("battle-cycle evidence path is unsafe")
    try:
        receipt = json.loads(
            receipt_path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("battle-cycle evidence is invalid") from None
    if not isinstance(receipt, Mapping):
        raise ProductFocusError("battle-cycle evidence is invalid")
    _validate_battle_cycle_projection(receipt)
    repeatable_evidence = _mapping_value(
        evidence[_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT + 1],
        subject="projected repeatable battle evidence",
    )
    if repeatable_evidence != {
        "kind": "unseen_comparison",
        "path": _REPEATABLE_BATTLE_RESULT_PATH,
        "sha256": _REPEATABLE_BATTLE_RESULT_SHA256,
    }:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    repeatable_path = (root / _REPEATABLE_BATTLE_RESULT_PATH).resolve()
    try:
        repeatable = json.loads(
            repeatable_path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("repeatable battle evidence is invalid") from None
    if not isinstance(repeatable, Mapping):
        raise ProductFocusError("repeatable battle evidence is invalid")
    _validate_repeatable_battle_projection(repeatable)
    first_authentic_evidence = _mapping_value(
        evidence[_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT + 2],
        subject="projected first authentic battle evidence",
    )
    if first_authentic_evidence != {
        "kind": "unseen_comparison",
        "path": _FIRST_AUTHENTIC_BATTLE_RESULT_PATH,
        "sha256": _FIRST_AUTHENTIC_BATTLE_RESULT_SHA256,
    }:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    first_authentic_path = (root / _FIRST_AUTHENTIC_BATTLE_RESULT_PATH).resolve()
    try:
        first_authentic = json.loads(
            first_authentic_path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("first authentic battle evidence is invalid") from None
    if not isinstance(first_authentic, Mapping):
        raise ProductFocusError("first authentic battle evidence is invalid")
    _validate_first_authentic_battle_projection(first_authentic)
    expected_utility_evidence = _mapping_value(
        evidence[_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT + 3],
        subject="projected expected-utility battle evidence",
    )
    if expected_utility_evidence != {
        "kind": "unseen_comparison",
        "path": _EXPECTED_UTILITY_BATTLE_RESULT_PATH,
        "sha256": _EXPECTED_UTILITY_BATTLE_RESULT_SHA256,
    }:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    expected_utility_path = (root / _EXPECTED_UTILITY_BATTLE_RESULT_PATH).resolve()
    try:
        expected_utility = json.loads(
            expected_utility_path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("expected-utility battle evidence is invalid") from None
    if not isinstance(expected_utility, Mapping):
        raise ProductFocusError("expected-utility battle evidence is invalid")
    _validate_expected_utility_battle_projection(expected_utility)
    player_evidence = _mapping_value(
        evidence[_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT + 4],
        subject="projected paired bounded-player evidence",
    )
    if player_evidence != {
        "kind": "verified_composition_episode",
        "path": _PAIRED_BOUNDED_PLAYER_RESULT_PATH,
        "sha256": _PAIRED_BOUNDED_PLAYER_RESULT_SHA256,
    }:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    player_path = (root / _PAIRED_BOUNDED_PLAYER_RESULT_PATH).resolve()
    try:
        player = json.loads(
            player_path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("paired bounded-player evidence is invalid") from None
    if not isinstance(player, Mapping):
        raise ProductFocusError("paired bounded-player evidence is invalid")
    _validate_paired_bounded_player_projection(player)
    causal_player_evidence = _mapping_value(
        evidence[_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT + 5],
        subject="projected causal player evidence",
    )
    if causal_player_evidence != {
        "kind": "unseen_comparison",
        "path": _CAUSAL_PLAYER_RESULT_PATH,
        "sha256": _CAUSAL_PLAYER_RESULT_SHA256,
    }:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    causal_player_path = (root / _CAUSAL_PLAYER_RESULT_PATH).resolve()
    try:
        causal_player = json.loads(
            causal_player_path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("causal player evidence is invalid") from None
    if not isinstance(causal_player, Mapping):
        raise ProductFocusError("causal player evidence is invalid")
    _validate_causal_player_projection(causal_player)
    calibration_evidence = _mapping_value(
        evidence[_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT + 6],
        subject="projected multi-goal calibration evidence",
    )
    if calibration_evidence != {
        "kind": "causal_train_example",
        "path": _MULTI_GOAL_CALIBRATION_PROGRESS_PATH,
        "sha256": _MULTI_GOAL_CALIBRATION_PROGRESS_SHA256,
    }:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    calibration_path = (root / _MULTI_GOAL_CALIBRATION_PROGRESS_PATH).resolve()
    try:
        calibration = json.loads(
            calibration_path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("multi-goal calibration evidence is invalid") from None
    if not isinstance(calibration, Mapping):
        raise ProductFocusError("multi-goal calibration evidence is invalid")
    _validate_multi_goal_calibration_projection(calibration)
    calibration_player_evidence = _mapping_value(
        evidence[_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT + 7],
        subject="projected calibration player evidence",
    )
    if calibration_player_evidence != {
        "kind": "composition_attempt",
        "path": _CALIBRATION_PLAYER_RESULT_PATH,
        "sha256": _CALIBRATION_PLAYER_RESULT_SHA256,
    }:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    calibration_player_path = (root / _CALIBRATION_PLAYER_RESULT_PATH).resolve()
    try:
        calibration_player = json.loads(
            calibration_player_path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError("calibration player evidence is invalid") from None
    if not isinstance(calibration_player, Mapping):
        raise ProductFocusError("calibration player evidence is invalid")
    _validate_calibration_player_projection(calibration_player)
    partial_player_evidence = _mapping_value(
        evidence[_PROJECTED_COUNTER_PREFIX_EVIDENCE_COUNT + 8],
        subject="projected calibration player partial evidence",
    )
    if partial_player_evidence != {
        "kind": "composition_attempt",
        "path": _CALIBRATION_PLAYER_PARTIAL_RESULT_PATH,
        "sha256": _CALIBRATION_PLAYER_PARTIAL_RESULT_SHA256,
    }:
        raise ProductFocusError(
            "active learning evidence lacks a supported counter projection"
        )
    partial_player_path = (
        root / _CALIBRATION_PLAYER_PARTIAL_RESULT_PATH
    ).resolve()
    try:
        partial_player = json.loads(
            partial_player_path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProductFocusError(
            "calibration player partial evidence is invalid"
        ) from None
    if not isinstance(partial_player, Mapping):
        raise ProductFocusError("calibration player partial evidence is invalid")
    _validate_calibration_player_partial_projection(partial_player)
    observed = {key: progress.get(key) for key in _PROJECTED_COUNTERS}
    if observed != _PROJECTED_COUNTERS:
        raise ProductFocusError(
            "active learning counters differ from their typed evidence projection"
        )


def _validate_paired_bounded_player_projection(
    receipt: Mapping[str, object],
) -> None:
    """Project one verified learned arm while retaining its baseline as a control."""

    if (
        receipt.get("schema")
        != "pokemon.red.paired-bounded-player-result-summary.v1"
        or receipt.get("status") != "complete_equivalent"
        or receipt.get("tracked_private_paths") != 0
        or receipt.get("private_path_fields") != 0
        or receipt.get("private_binding_fields") != 0
    ):
        raise ProductFocusError("paired bounded-player evidence status differs")
    delta = _mapping(
        receipt,
        "learning_counter_delta",
        subject="paired bounded-player evidence",
    )
    if delta != {
        "composition_attempts_development": 1,
        "development_episode_attempts": 1,
        "verified_composition_episodes_development": 1,
    }:
        raise ProductFocusError("paired bounded-player counter delta differs")
    comparison = _mapping(
        receipt,
        "comparison",
        subject="paired bounded-player evidence",
    )
    if (
        comparison.get("verdict") != "equivalent"
        or comparison.get("decision_basis") != "equal_progress_and_cost"
        or comparison.get("storage_headroom_gained_each") != 18
        or comparison.get("specimen_loss_each") != 0
    ):
        raise ProductFocusError("paired bounded-player comparison differs")
    arms = _mapping(receipt, "arms", subject="paired bounded-player evidence")
    learned = _mapping(arms, "learned", subject="paired bounded-player arms")
    baseline = _mapping(arms, "baseline", subject="paired bounded-player arms")
    for arm, authority in (
        (learned, "learned-goal-manager"),
        (baseline, "completion-first-teacher"),
    ):
        if {
            "actions": arm.get("actions"),
            "authority_id": arm.get("authority_id"),
            "completion_satisfied": arm.get("completion_satisfied"),
            "decisions": arm.get("decisions"),
            "frames": arm.get("frames"),
            "recovery_attempts": arm.get("recovery_attempts"),
            "selected_goal": arm.get("selected_goal"),
            "status": arm.get("status"),
            "storage_headroom_after": arm.get("storage_headroom_after"),
            "storage_headroom_before": arm.get("storage_headroom_before"),
        } != {
            "actions": 36,
            "authority_id": authority,
            "completion_satisfied": True,
            "decisions": 1,
            "frames": 4512,
            "recovery_attempts": 0,
            "selected_goal": "manage_storage",
            "status": "succeeded",
            "storage_headroom_after": 20,
            "storage_headroom_before": 2,
        }:
            raise ProductFocusError("paired bounded-player arm differs")
    interpretation = _mapping(
        receipt,
        "interpretation",
        subject="paired bounded-player evidence",
    )
    if interpretation.get("authority_promoted") is not False:
        raise ProductFocusError("paired bounded-player authority claim differs")


def _validate_causal_player_projection(receipt: Mapping[str, object]) -> None:
    """Project one same-state causal-manager advantage without broad promotion."""

    if receipt.get("schema") != "pokemon.red.causal-player-pair-result.v1":
        raise ProductFocusError("causal player evidence schema differs")
    if receipt.get("status") != "complete":
        raise ProductFocusError("causal player evidence status differs")
    comparison = _mapping(receipt, "comparison", subject="causal player evidence")
    if (
        comparison.get("pair_id") != "red-causal-player-pair-003"
        or comparison.get("verdict") != "learned_advantage"
        or comparison.get("decision_basis") != "verified_progress_dominance"
        or comparison.get("equal_starting_state") is not True
        or comparison.get("equal_starting_semantic_state") is not True
        or comparison.get("equal_starting_collection") is not True
    ):
        raise ProductFocusError("causal player comparison differs")
    challenger = _mapping(receipt, "challenger", subject="causal player evidence")
    if {
        "actions": challenger.get("actions"),
        "frames": challenger.get("frames"),
        "selected_goal": challenger.get("selected_goal"),
        "status": challenger.get("status"),
        "target_level_before": challenger.get("target_level_before"),
        "target_level_after": challenger.get("target_level_after"),
    } != {
        "actions": 1119,
        "frames": 101171,
        "selected_goal": "develop_team",
        "status": "succeeded",
        "target_level_before": 20,
        "target_level_after": 21,
    }:
        raise ProductFocusError("causal player challenger differs")
    baseline = _mapping(receipt, "baseline", subject="causal player evidence")
    if {
        "actions": baseline.get("actions"),
        "frames": baseline.get("frames"),
        "selected_goal": baseline.get("selected_goal"),
        "status": baseline.get("status"),
        "failure_reason": baseline.get("failure_reason"),
        "target_level_before": baseline.get("target_level_before"),
        "target_level_after": baseline.get("target_level_after"),
        "target_evolved": baseline.get("target_evolved"),
    } != {
        "actions": 6000,
        "frames": 257689,
        "selected_goal": "evolve_species",
        "status": "failed",
        "failure_reason": "execution_budget_exhausted",
        "target_level_before": 22,
        "target_level_after": 23,
        "target_evolved": False,
    }:
        raise ProductFocusError("causal player baseline differs")
    learning = _mapping(receipt, "learning_effect", subject="causal player evidence")
    authority = _mapping(receipt, "authority_effect", subject="causal player evidence")
    scope = _mapping(receipt, "scope", subject="causal player evidence")
    if (
        learning.get("development_comparison_delta") != 1
        or learning.get("fit_count_delta") != 0
        or learning.get("production_authority_delta") != 0
        or authority.get("broader_authority_promoted") is not False
        or authority.get("teacher_queries") != 0
        or authority.get("teacher_fallbacks") != 0
        or scope.get("sealed_red_accesses") != 0
        or scope.get("crystal_accesses") != 0
        or scope.get("full_game_replays") != 0
        or scope.get("private_path_fields") != 0
        or scope.get("private_binding_fields") != 0
    ):
        raise ProductFocusError("causal player protected boundary differs")


def _validate_multi_goal_calibration_projection(receipt: Mapping[str, object]) -> None:
    """Project only independently admitted fixed-arm outcomes into train counters."""

    if {
        "schema": receipt.get("schema"),
        "status": receipt.get("status"),
        "admission_reader_ci_run_id": receipt.get("admission_reader_ci_run_id"),
        "admission_reader_source_commit": receipt.get(
            "admission_reader_source_commit"
        ),
        "campaign_plan_sha256": receipt.get("campaign_plan_sha256"),
        "admitted_outcomes": receipt.get("admitted_outcomes"),
        "admitted_succeeded_outcomes": receipt.get(
            "admitted_succeeded_outcomes"
        ),
        "admitted_failed_outcomes": receipt.get("admitted_failed_outcomes"),
        "consumed_unusable_trials": receipt.get("consumed_unusable_trials"),
        "untouched_trials": receipt.get("untouched_trials"),
        "collection_regressions": receipt.get("collection_regressions"),
        "teacher_queries": receipt.get("teacher_queries"),
        "model_fits": receipt.get("model_fits"),
        "model_predictions": receipt.get("model_predictions"),
        "private_path_fields": receipt.get("private_path_fields"),
        "promotion_authorized": receipt.get("promotion_authorized"),
    } != {
        "schema": "pokemon.red.multi-goal-calibration-progress.v1",
        "status": "completed-train-only-calibration-fit",
        "admission_reader_ci_run_id": 33834577946,
        "admission_reader_source_commit": (
            "a16fc0d8d85c5560b43b55116b594cfae543f488"
        ),
        "campaign_plan_sha256": (
            "1fc47b008d5159ea42d81286f1989be4ca3e70d9d99a1427507c87d4a02b3267"
        ),
        "admitted_outcomes": 7,
        "admitted_succeeded_outcomes": 4,
        "admitted_failed_outcomes": 3,
        "consumed_unusable_trials": 2,
        "untouched_trials": 0,
        "collection_regressions": 0,
        "teacher_queries": 0,
        "model_fits": 1,
        "model_predictions": 7,
        "private_path_fields": 0,
        "promotion_authorized": False,
    }:
        raise ProductFocusError("multi-goal calibration projection differs")
    trials = _sequence(receipt, "trials", subject="multi-goal calibration evidence")
    if len(trials) != 9:
        raise ProductFocusError("multi-goal calibration trial denominator differs")
    expected = (
        (0, "advance_story", "invalid-no-retry", None, 0),
        (1, "develop_team", None, "admitted", 2009),
        (2, "develop_team", None, "admitted", 1179),
        (3, "advance_story", None, "admitted", 6000),
        (4, "evolve_species", None, "admitted", 6000),
        (5, "advance_story", "invalid-no-retry", None, 0),
        (6, "manage_storage", None, "admitted", 36),
        (7, "advance_story", None, "admitted", 0),
        (8, "manage_storage", None, "admitted", 36),
    )
    observed = tuple(
        (
            _mapping_value(item, subject="multi-goal calibration trial").get(
                "trial_ordinal"
            ),
            _mapping_value(item, subject="multi-goal calibration trial").get(
                "goal_kind"
            ),
            _mapping_value(item, subject="multi-goal calibration trial").get(
                "disposition"
            ),
            _mapping_value(item, subject="multi-goal calibration trial").get(
                "admission"
            ),
            _mapping_value(item, subject="multi-goal calibration trial").get(
                "actions_executed",
                _mapping_value(item, subject="multi-goal calibration trial").get(
                    "controller_actions"
                ),
            ),
        )
        for item in trials
    )
    if observed != expected:
        raise ProductFocusError("multi-goal calibration trial projection differs")
    fit = _mapping(receipt, "fit", subject="multi-goal calibration evidence")
    if {
        "base_model_canonical_sha256": fit.get("base_model_canonical_sha256"),
        "candidate_model_canonical_sha256": fit.get(
            "candidate_model_canonical_sha256"
        ),
        "candidate_model_file_sha256": fit.get("candidate_model_file_sha256"),
        "summary_file_sha256": fit.get("summary_file_sha256"),
        "training_loss_before": fit.get("training_loss_before"),
        "training_loss_after": fit.get("training_loss_after"),
        "maximum_guard_menu_kl": fit.get("maximum_guard_menu_kl"),
        "maximum_guard_menu_kl_cap": fit.get("maximum_guard_menu_kl_cap"),
        "update_steps": fit.get("update_steps"),
        "same_bank_calibration_only": fit.get("same_bank_calibration_only"),
        "private_path_fields": fit.get("private_path_fields"),
    } != {
        "base_model_canonical_sha256": (
            "af29d7e7f72e9921e638c88664b17e6fbbf6334468609ab66bda41c9f3dad66d"
        ),
        "candidate_model_canonical_sha256": (
            "70a72bdb084fbfe3ae8eccf68b582a3503ebbc5f07428616ddeb4e9d78416bcb"
        ),
        "candidate_model_file_sha256": (
            "5fc8106d7223824f1bbb422c23f89a1f18cc071edc144ef8971fc85d84cd6f40"
        ),
        "summary_file_sha256": (
            "01281fb58901b4557ef0a2c626c39b89607cfc837734fa6d96a77d61b139e4d2"
        ),
        "training_loss_before": 1.2526772559519361,
        "training_loss_after": 1.2481073745536153,
        "maximum_guard_menu_kl": 0.0017115827744108268,
        "maximum_guard_menu_kl_cap": 0.01,
        "update_steps": 1,
        "same_bank_calibration_only": True,
        "private_path_fields": 0,
    }:
        raise ProductFocusError("multi-goal calibration fit projection differs")


def _validate_calibration_player_projection(receipt: Mapping[str, object]) -> None:
    """Project the complete singleton-stop pair without inventing strategic progress."""

    if (
        receipt.get("schema") != "pokemon.red.calibration-player-pair-result.v1"
        or receipt.get("status") != "complete_equivalent_singleton_stop"
    ):
        raise ProductFocusError("calibration player evidence status differs")
    comparison = _mapping(receipt, "comparison", subject="calibration player evidence")
    if {
        "pair_id": comparison.get("pair_id"),
        "verdict": comparison.get("verdict"),
        "decision_basis": comparison.get("decision_basis"),
        "equal_starting_state": comparison.get("equal_starting_state"),
        "equal_starting_semantic_state": comparison.get(
            "equal_starting_semantic_state"
        ),
        "equal_starting_collection": comparison.get("equal_starting_collection"),
        "authority_disagreement": comparison.get("authority_disagreement"),
        "model_strategic_decisions": comparison.get("model_strategic_decisions"),
        "safety_override_decisions": comparison.get("safety_override_decisions"),
        "living_collection_regressions": comparison.get(
            "living_collection_regressions"
        ),
    } != {
        "pair_id": "red-calibration-player-pair-004",
        "verdict": "equivalent",
        "decision_basis": "equal_progress_and_cost",
        "equal_starting_state": True,
        "equal_starting_semantic_state": True,
        "equal_starting_collection": True,
        "authority_disagreement": False,
        "model_strategic_decisions": 0,
        "safety_override_decisions": 2,
        "living_collection_regressions": 0,
    }:
        raise ProductFocusError("calibration player comparison differs")
    arms = _mapping(receipt, "arms", subject="calibration player evidence")
    for key, authority, manifest in (
        (
            "calibration_model",
            "multi-goal-calibration-shadow",
            "46128596f4f625da550e04b7489186aaaece5719eb7f7f35116149ee88a55e3b",
        ),
        (
            "baseline",
            "completion-first-teacher",
            "f3916eeb0e3364deda2a6a30029c76de6b1a857b04ebbde23858de3692dbb3a8",
        ),
    ):
        arm = _mapping(arms, key, subject="calibration player arms")
        if {
            "authority_id": arm.get("authority_id"),
            "status": arm.get("status"),
            "stop_reason": arm.get("stop_reason"),
            "decisions": arm.get("decisions"),
            "selected_goal": arm.get("selected_goal"),
            "actions": arm.get("actions"),
            "frames": arm.get("frames"),
            "specimens_before": arm.get("specimens_before"),
            "specimens_after": arm.get("specimens_after"),
            "required_specimens_reduced": arm.get("required_specimens_reduced"),
            "trajectory_manifest_sha256": arm.get("trajectory_manifest_sha256"),
        } != {
            "authority_id": authority,
            "status": "durable_terminal",
            "stop_reason": "insufficient_available_goals",
            "decisions": 1,
            "selected_goal": "restore_team",
            "actions": 188,
            "frames": 17136,
            "specimens_before": 15,
            "specimens_after": 15,
            "required_specimens_reduced": 0,
            "trajectory_manifest_sha256": manifest,
        }:
            raise ProductFocusError("calibration player arm differs")
    counters = _mapping(
        receipt,
        "counter_treatment",
        subject="calibration player evidence",
    )
    if counters != {
        "authority_promotions_added": 0,
        "causal_train_examples_added": 0,
        "composition_attempts_added": 1,
        "development_episode_attempts_added": 2,
        "model_fits_added": 0,
        "transfer_results_added": 0,
        "unseen_comparisons_added": 0,
        "verified_composition_episodes_added": 0,
    }:
        raise ProductFocusError("calibration player counter treatment differs")
    scope = _mapping(receipt, "scope", subject="calibration player evidence")
    if scope != {
        "crystal_accesses": 0,
        "full_game_replays": 0,
        "private_binding_fields": 0,
        "private_path_fields": 0,
        "sealed_red_accesses": 0,
        "teacher_fallbacks": 0,
        "teacher_queries": 0,
    }:
        raise ProductFocusError("calibration player protected boundary differs")


def _validate_calibration_player_partial_projection(
    receipt: Mapping[str, object],
) -> None:
    """Project pair 005 as one partial attempt, never as a comparison or fit."""

    if (
        receipt.get("schema")
        != "pokemon.red.calibration-player-partial-result.v1"
        or receipt.get("status") != "partial_challenger_binding_failure"
    ):
        raise ProductFocusError("calibration player partial status differs")
    comparison = _mapping(
        receipt,
        "comparison",
        subject="calibration player partial evidence",
    )
    if comparison != {
        "baseline_actions": 0,
        "baseline_started": False,
        "pair_id": "red-calibration-player-pair-005",
        "paired_verdict": None,
        "replay_allowed": False,
    }:
        raise ProductFocusError("calibration player partial comparison differs")
    arm = _mapping(
        receipt,
        "challenger_arm",
        subject="calibration player partial evidence",
    )
    if {
        "authority_id": arm.get("authority_id"),
        "terminal_status": arm.get("terminal_status"),
        "durable_goal_outcomes": arm.get("durable_goal_outcomes"),
        "actions": arm.get("actions"),
        "frames": arm.get("frames"),
        "partial_episode_manifest_file_sha256": arm.get(
            "partial_episode_manifest_file_sha256"
        ),
    } != {
        "authority_id": "multi-goal-calibration-shadow",
        "terminal_status": "failed_partial",
        "durable_goal_outcomes": 3,
        "actions": 614,
        "frames": 34920,
        "partial_episode_manifest_file_sha256": (
            "299edd5b89a4599ec1a92ac671a50511d789c56573e7ba47f9de158c3e7021c6"
        ),
    }:
        raise ProductFocusError("calibration player partial arm differs")
    decisions = _sequence(
        arm,
        "decisions",
        subject="calibration player partial arm",
    )
    if [
        (
            _mapping_value(item, subject="calibration player partial decision").get(
                "goal"
            ),
            _mapping_value(item, subject="calibration player partial decision").get(
                "status"
            ),
            _mapping_value(item, subject="calibration player partial decision").get(
                "failure_reason"
            ),
        )
        for item in decisions
    ] != [
        ("acquire_species", "succeeded", None),
        ("acquire_species", "succeeded", None),
        ("acquire_species", "failed", "binding_failed"),
    ]:
        raise ProductFocusError("calibration player partial decisions differ")
    counters = _mapping(
        receipt,
        "counter_treatment",
        subject="calibration player partial evidence",
    )
    if counters != {
        "authority_promotions_added": 0,
        "causal_train_examples_added": 0,
        "composition_attempts_added": 1,
        "development_episode_attempts_added": 1,
        "model_fits_added": 0,
        "transfer_results_added": 0,
        "unseen_comparisons_added": 0,
        "verified_composition_episodes_added": 0,
    }:
        raise ProductFocusError("calibration player partial counters differ")
    scope = _mapping(
        receipt,
        "scope",
        subject="calibration player partial evidence",
    )
    if scope != {
        "crystal_accesses": 0,
        "full_game_replays": 0,
        "model_strategic_decisions": 3,
        "private_binding_fields": 0,
        "private_path_fields": 0,
        "sealed_red_accesses": 0,
        "teacher_fallbacks": 0,
        "teacher_queries": 0,
    }:
        raise ProductFocusError("calibration player partial boundary differs")


def _validate_battle_cycle_projection(receipt: Mapping[str, object]) -> None:
    """Project only the retained, rejected one-pair cycle into honest counters."""

    if (
        receipt.get("schema") != "pokemon.red.battle-outcome-cycle-result.v1"
        or receipt.get("status") != "rejected_no_development_discordance"
    ):
        raise ProductFocusError("battle-cycle evidence status differs")
    source = _mapping(receipt, "source_verification", subject="battle-cycle evidence")
    if (
        source.get("git_commit")
        != "1d9554923f7973d6c3807445c1c4fc19c65dca1b"
        or source.get("exact_main_ci_run") != 33424040364
        or source.get("exact_main_ci_attempt") != 1
        or source.get("exact_main_ci_conclusion") != "success"
        or source.get("worktree_dirty") is not False
    ):
        raise ProductFocusError("battle-cycle source verification differs")
    execution = _mapping(receipt, "execution", subject="battle-cycle evidence")
    if {
        "root_claims_created": execution.get("root_claims_created"),
        "candidate_claims_created": execution.get("candidate_claims_created"),
        "activated_candidate_targets": execution.get("activated_candidate_targets"),
        "measured_candidate_outcomes": execution.get("measured_candidate_outcomes"),
        "train_candidate_outcomes": execution.get("train_candidate_outcomes"),
        "development_candidate_outcomes": execution.get(
            "development_candidate_outcomes"
        ),
        "unexecuted_counterfactual_targets": execution.get(
            "unexecuted_counterfactual_targets"
        ),
        "unmeasured_action_targets": execution.get("unmeasured_action_targets"),
        "teacher_queries": execution.get("teacher_queries"),
        "teacher_choice_targets": execution.get("teacher_choice_targets"),
    } != {
        "root_claims_created": 2,
        "candidate_claims_created": 6,
        "activated_candidate_targets": 6,
        "measured_candidate_outcomes": 6,
        "train_candidate_outcomes": 3,
        "development_candidate_outcomes": 3,
        "unexecuted_counterfactual_targets": 0,
        "unmeasured_action_targets": 0,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
    }:
        raise ProductFocusError("battle-cycle measured target projection differs")
    update = _mapping(receipt, "train_update", subject="battle-cycle evidence")
    development = _mapping(
        receipt,
        "development_comparison",
        subject="battle-cycle evidence",
    )
    if (
        update.get("training_examples") != 1
        or update.get("model_fits") != 1
        or update.get("development_influenced_fit") is not False
        or development.get("examples") != 1
        or development.get("predictions_committed_before_outcomes") is not True
        or development.get("discordant_examples") != 0
        or development.get("equivalent_choices") != 1
        or development.get("candidate_advantage_observed") is not False
        or development.get("inferential_claim") is not False
    ):
        raise ProductFocusError("battle-cycle update or comparison projection differs")
    counters = _mapping(receipt, "counter_treatment", subject="battle-cycle evidence")
    if counters != {
        "authority_promotions_added": 0,
        "causal_train_examples_added": 1,
        "development_episode_attempts_added": 1,
        "model_fits_added": 1,
        "transfer_results_added": 0,
        "unseen_comparisons_added": 0,
        "verified_outcome_examples_added": 1,
    }:
        raise ProductFocusError("battle-cycle counter treatment differs")
    protected = _mapping(receipt, "protected_access", subject="battle-cycle evidence")
    if (
        protected.get("authority_promoted") is not False
        or protected.get("sealed_red_cases_opened") != 0
        or protected.get("crystal_contexts_opened") != 0
        or protected.get("full_game_replays") != 0
        or protected.get("private_identity_fields") != 0
        or protected.get("private_path_fields") != 0
    ):
        raise ProductFocusError("battle-cycle protected access differs")


def _validate_repeatable_battle_projection(receipt: Mapping[str, object]) -> None:
    """Project the repeatable authentic development loop into honest counters."""

    if (
        receipt.get("schema")
        != "pokemon-public-repeatable-red-battle-learning-result-v1"
        or receipt.get("status") != "development_pass"
    ):
        raise ProductFocusError("repeatable battle evidence status differs")
    adaptation = _mapping(
        receipt,
        "authentic_adaptation",
        subject="repeatable battle evidence",
    )
    independent = _mapping(
        receipt,
        "independent_development",
        subject="repeatable battle evidence",
    )
    rehearsal = _mapping(
        receipt,
        "fresh_live_authority_rehearsal",
        subject="repeatable battle evidence",
    )
    boundaries = _mapping(
        receipt,
        "boundaries",
        subject="repeatable battle evidence",
    )
    if (
        adaptation.get("train_roots") != 12
        or adaptation.get("development_roots") != 7
        or adaptation.get("informative_examples") != 19
        or adaptation.get("base_development_accuracy") != 5 / 7
        or adaptation.get("updated_development_accuracy") != 1.0
        or independent.get("roots") != 7
        or independent.get("base_correct") != 2
        or independent.get("updated_correct") != 5
        or independent.get("inferential_claim") is not False
        or rehearsal.get("model_selected_actions") != 1
        or rehearsal.get("teacher_queries") != 0
        or rehearsal.get("choice_was_counterfactually_optimal") is not True
    ):
        raise ProductFocusError("repeatable battle learning projection differs")
    if (
        boundaries.get("development_artifact") is not True
        or boundaries.get("sealed_red_cases_opened") != 0
        or boundaries.get("crystal_contexts_opened") != 0
        or boundaries.get("full_game_replays") != 0
        or boundaries.get("teacher_choice_targets") != 0
        or boundaries.get("gameplay_authority_promoted") is not False
        or boundaries.get("transfer_claim") is not False
        or boundaries.get("private_path_fields") != 0
    ):
        raise ProductFocusError("repeatable battle protected access differs")


def _validate_first_authentic_battle_projection(receipt: Mapping[str, object]) -> None:
    """Project the first cartridge-grounded train/fit/development result."""

    if receipt.get("schema") != "pokemon.core.battle.repeatable-first-authentic-result.v1":
        raise ProductFocusError("first authentic battle evidence schema differs")
    train = _mapping(receipt, "train", subject="first authentic battle evidence")
    model = _mapping(receipt, "model", subject="first authentic battle evidence")
    development = _mapping(
        receipt,
        "development",
        subject="first authentic battle evidence",
    )
    interpretation = _mapping(
        receipt,
        "interpretation",
        subject="first authentic battle evidence",
    )
    if (
        train.get("complete_examples") != 41
        or train.get("fit_examples") != 40
        or train.get("root_lineages") != 4
        or train.get("semantic_clusters") != 35
        or model.get("loss_before") != 2.6713800625569695
        or model.get("loss_after") != 1.024249795532914
        or development.get("complete_examples") != 21
        or development.get("root_lineages") != 4
        or development.get("predictions_committed_before_outcomes") != 24
        or development.get("base_correct_preferences") != 16
        or development.get("updated_correct_preferences") != 17
        or development.get("fixed_heuristic_correct_preferences") != 18
        or interpretation.get("base_improved") is not True
        or interpretation.get("fixed_heuristic_beaten") is not False
        or interpretation.get("stochastic_label_aliasing_observed") is not True
    ):
        raise ProductFocusError("first authentic battle learning projection differs")
    if (
        receipt.get("authority_promoted") is not False
        or receipt.get("teacher_queries") != 0
        or receipt.get("full_game_replays") != 0
        or receipt.get("sealed_red_cases_opened") != 0
        or receipt.get("crystal_contexts_opened") != 0
        or receipt.get("private_path_fields") != 0
    ):
        raise ProductFocusError("first authentic battle protected access differs")


def _validate_expected_utility_battle_projection(receipt: Mapping[str, object]) -> None:
    """Project the repeated-RNG fit and fresh development rejection."""

    if receipt.get("schema") != "pokemon.core.battle.expected-utility-result.v1":
        raise ProductFocusError("expected-utility battle evidence schema differs")
    train = _mapping(
        _mapping(receipt, "collection", subject="expected-utility battle evidence"),
        "train",
        subject="expected-utility battle evidence",
    )
    development = _mapping(
        _mapping(receipt, "collection", subject="expected-utility battle evidence"),
        "development",
        subject="expected-utility battle evidence",
    )
    fit = _mapping(receipt, "fit", subject="expected-utility battle evidence")
    comparison = _mapping(
        receipt,
        "development_comparison",
        subject="expected-utility battle evidence",
    )
    base = _mapping(comparison, "base", subject="expected-utility battle evidence")
    challenger = _mapping(
        comparison,
        "challenger",
        subject="expected-utility battle evidence",
    )
    heuristic = _mapping(
        comparison,
        "fixed_heuristic",
        subject="expected-utility battle evidence",
    )
    verdict = _mapping(receipt, "verdict", subject="expected-utility battle evidence")
    if (
        train.get("examples") != 32
        or train.get("root_lineages") != 4
        or train.get("trials_complete") != 260
        or development.get("examples") != 20
        or development.get("root_lineages") != 4
        or development.get("trials_complete") != 151
        or fit.get("balanced_training_examples") != 20
        or fit.get("loss_before") != 0.9460775652955935
        or fit.get("loss_after") != 0.7789484125679926
        or base.get("correct_preferences") != 17
        or challenger.get("correct_preferences") != 18
        or heuristic.get("correct_preferences") != 20
        or verdict.get("promotion_gate_passed") is not False
        or verdict.get("challenger_status") != "shadow_only"
        or verdict.get("battle_authority") != "fixed_heuristic_retained"
    ):
        raise ProductFocusError("expected-utility battle projection differs")
    effects = _mapping(receipt, "effects", subject="expected-utility battle evidence")
    if (
        receipt.get("authority_promoted") is not False
        or effects.get("teacher_queries") != 0
        or effects.get("full_game_replays") != 0
        or effects.get("sealed_red_cases_opened") != 0
        or effects.get("crystal_executions") != 0
    ):
        raise ProductFocusError("expected-utility battle protected access differs")


def _validate_rigor_policy(policy: Mapping[str, object]) -> None:
    _require_keys(policy, _RIGOR_TIERS, subject="rigor policy")
    for tier in _RIGOR_TIERS:
        entry = _mapping(policy, tier, subject="rigor policy")
        _require_keys(
            entry,
            {
                "exact_source_ci_binding",
                "external_review",
                "owner_authorization_per_case",
                "purpose",
                "repeatable",
            },
            subject=f"{tier} rigor",
        )
        _bool(entry, "repeatable", subject=f"{tier} rigor")
        _bool(entry, "owner_authorization_per_case", subject=f"{tier} rigor")
        _bool(entry, "exact_source_ci_binding", subject=f"{tier} rigor")
        _text(entry, "external_review", subject=f"{tier} rigor")
        _text(entry, "purpose", subject=f"{tier} rigor")
    development = _mapping(policy, "development", subject="rigor policy")
    benchmark = _mapping(policy, "benchmark", subject="rigor policy")
    sealed = _mapping(policy, "sealed", subject="rigor policy")
    if (
        not _bool(development, "repeatable", subject="development rigor")
        or _bool(
            development,
            "owner_authorization_per_case",
            subject="development rigor",
        )
        or _bool(development, "exact_source_ci_binding", subject="development rigor")
    ):
        raise ProductFocusError("development rigor must preserve a fast repeatable loop")
    if not _bool(benchmark, "exact_source_ci_binding", subject="benchmark rigor"):
        raise ProductFocusError("benchmark rigor must bind exact source and CI")
    if (
        _bool(sealed, "repeatable", subject="sealed rigor")
        or not _bool(
            sealed,
            "owner_authorization_per_case",
            subject="sealed rigor",
        )
        or not _bool(sealed, "exact_source_ci_binding", subject="sealed rigor")
    ):
        raise ProductFocusError("sealed rigor must remain one-shot and owner-authorized")


def _validate_session_budget(budget: Mapping[str, object]) -> None:
    _require_keys(
        budget,
        {"data_and_scenarios", "maintenance_and_docs", "model_and_evaluation"},
        subject="session budget",
    )
    data = _count(budget, "data_and_scenarios", subject="session budget")
    model = _count(budget, "model_and_evaluation", subject="session budget")
    maintenance = _count(budget, "maintenance_and_docs", subject="session budget")
    if data + model + maintenance != 100:
        raise ProductFocusError("session budget must sum to 100 percent")
    if data + model < 75 or maintenance > 25:
        raise ProductFocusError("session budget gives too little time to learning work")


def _validate_alarms(alarms: Mapping[str, object]) -> None:
    _require_keys(
        alarms,
        {
            "maximum_consecutive_ci_only_repairs",
            "maximum_full_replays_during_active_lane",
            "maximum_sessions_without_measured_learning_output",
            "stop_on_repeated_fixed_route_patch",
            "stop_on_unmeasured_teacher_label_copy",
        },
        subject="alarms",
    )
    if (
        _count(
            alarms,
            "maximum_sessions_without_measured_learning_output",
            subject="alarms",
        )
        > 1
    ):
        raise ProductFocusError("learning-output alarm cannot exceed one session")
    if _count(alarms, "maximum_consecutive_ci_only_repairs", subject="alarms") > 1:
        raise ProductFocusError("CI-only repair alarm cannot exceed one repair")
    if _count(alarms, "maximum_full_replays_during_active_lane", subject="alarms") != 0:
        raise ProductFocusError("active development lane cannot permit a full replay")
    if not _bool(alarms, "stop_on_repeated_fixed_route_patch", subject="alarms"):
        raise ProductFocusError("fixed-route drift alarm must remain enabled")
    if not _bool(alarms, "stop_on_unmeasured_teacher_label_copy", subject="alarms"):
        raise ProductFocusError("teacher-label drift alarm must remain enabled")


def _validate_status_report(status: Mapping[str, object]) -> None:
    _require_keys(status, {"counter_source", "required_fields"}, subject="status report")
    _text(status, "counter_source", subject="status report")
    fields = set(_text_sequence(status, "required_fields", subject="status report"))
    if fields != _REQUIRED_STATUS_FIELDS:
        raise ProductFocusError("status report fields do not cover the required product truth")


def _validate_review_roles(roles: Mapping[str, object]) -> None:
    _require_keys(roles, {"antigravity", "claude", "codex"}, subject="review roles")
    for role in ("codex", "claude", "antigravity"):
        _text(roles, role, subject="review roles")


def _current_output_count(
    progress: Mapping[str, object],
    output: Mapping[str, object],
) -> int:
    kind = _text(output, "kind", subject="measurable output")
    partition = _text(output, "partition", subject="measurable output")
    if kind == "outcome_question":
        outcomes = _mapping(progress, "outcome_questions", subject="active lane progress")
        if partition not in {"train", "development"}:
            raise ProductFocusError("outcome question must use train or development partition")
        return _count(outcomes, partition, subject="outcome progress")
    progress_key = {
        "atomic_goal_episode": "atomic_goal_episodes",
        "authority_promotion": "authority_promotions",
        "causal_train_example": "causal_train_examples",
        "composition_attempt": "composition_attempts",
        "development_episode": "development_episode_attempts",
        "model_fit": "model_fits",
        "synthetic_rootless_atomic_goal_episode": ("synthetic_rootless_atomic_goal_episodes"),
        "synthetic_rootless_model_fit": "synthetic_rootless_model_fits",
        "synthetic_rootless_train_outcome": "synthetic_rootless_train_outcomes",
        "synthetic_rootless_unseen_comparison": (
            "synthetic_rootless_unseen_comparisons"
        ),
        "transfer_result": "transfer_results",
        "unseen_comparison": "unseen_comparisons",
        "verified_composition_episode": "verified_composition_episodes",
        "verified_outcome_example": "verified_outcome_examples",
    }.get(kind)
    if progress_key is None:
        raise ProductFocusError("measurable output has no progress counter")
    return _count(progress, progress_key, subject="active lane progress")


def _current_progress_counts(progress: Mapping[str, object]) -> tuple[int, ...]:
    outcomes = _mapping(progress, "outcome_questions", subject="active lane progress")
    return (
        _count(outcomes, "train", subject="outcome progress"),
        _count(outcomes, "development", subject="outcome progress"),
        _count(progress, "model_fits", subject="active lane progress"),
        _count(progress, "unseen_comparisons", subject="active lane progress"),
        _count(progress, "authority_promotions", subject="active lane progress"),
        _count(progress, "transfer_results", subject="active lane progress"),
        _count(progress, "development_episode_attempts", subject="active lane progress"),
        _count(progress, "verified_outcome_examples", subject="active lane progress"),
        _count(progress, "atomic_goal_episodes", subject="active lane progress"),
        _count(progress, "causal_train_examples", subject="active lane progress"),
        _count(progress, "composition_attempts", subject="active lane progress"),
        _count(progress, "verified_composition_episodes", subject="active lane progress"),
        _count(
            progress,
            "synthetic_rootless_train_outcomes",
            subject="active lane progress",
        ),
        _count(
            progress,
            "synthetic_rootless_atomic_goal_episodes",
            subject="active lane progress",
        ),
        _count(
            progress,
            "synthetic_rootless_model_fits",
            subject="active lane progress",
        ),
        _count(
            progress,
            "synthetic_rootless_unseen_comparisons",
            subject="active lane progress",
        ),
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    del value
    raise ValueError("non-finite JSON number")


def _require_keys(
    value: Mapping[str, object],
    expected: set[str],
    *,
    subject: str,
) -> None:
    if set(value) != expected:
        raise ProductFocusError(f"{subject} fields are incomplete or unsupported")


def _mapping(
    source: Mapping[str, object],
    key: str,
    *,
    subject: str,
) -> Mapping[str, object]:
    return _mapping_value(source.get(key), subject=f"{subject} {key.replace('_', ' ')}")


def _mapping_value(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProductFocusError(f"{subject} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ProductFocusError(f"{subject} keys must be text")
    return value


def _sequence(
    source: Mapping[str, object],
    key: str,
    *,
    subject: str,
) -> Sequence[object]:
    value = source.get(key)
    if not isinstance(value, list):
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be a list")
    return value


def _text(
    source: Mapping[str, object],
    key: str,
    *,
    subject: str,
    maximum: int = 500,
) -> str:
    value = source.get(key)
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > maximum
        or any(character in value for character in ("\n", "\r", "\x00"))
    ):
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be one-line text")
    return value


def _identifier(source: Mapping[str, object], key: str, *, subject: str) -> str:
    value = _text(source, key, subject=subject, maximum=96)
    if _IDENTIFIER.fullmatch(value) is None:
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} is not an identifier")
    return value


def _text_sequence(
    source: Mapping[str, object],
    key: str,
    *,
    subject: str,
) -> tuple[str, ...]:
    values = _sequence(source, key, subject=subject)
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ProductFocusError(f"{subject} {key.replace('_', ' ')} contains non-text")
        item = {"value": value}
        result.append(_text(item, "value", subject=subject))
    if len(result) != len(set(result)):
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} contains duplicates")
    return tuple(result)


def _count(source: Mapping[str, object], key: str, *, subject: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be a count")
    return value


def _positive_int(source: Mapping[str, object], key: str, *, subject: str) -> int:
    value = _count(source, key, subject=subject)
    if value < 1:
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be positive")
    return value


def _bool(source: Mapping[str, object], key: str, *, subject: str) -> bool:
    value = source.get(key)
    if not isinstance(value, bool):
        raise ProductFocusError(f"{subject} {key.replace('_', ' ')} must be boolean")
    return value


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _table_text(value: str) -> str:
    return value.replace("|", "\\|")


def _table_row(label: str, value: str) -> str:
    return f"| {label} | {_table_text(value)} |"
