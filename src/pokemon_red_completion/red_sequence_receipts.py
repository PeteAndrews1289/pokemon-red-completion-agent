"""Read-only projection of existing continuous-player records for design checks.

This authenticates pinned documents, state bytes, ordering and counter ownership.
It does NOT independently decode cartridge facts, reconstruct private executor
mapping or admit TRAIN data. The existing native auditor remains required for
those claims. A historical projection cannot create prospective window authority.
"""

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from .living_dex_policy_codec import restore_living_dex_policy_menu
from .player_short_sequence import MeasuredSequenceStep, SequencePreview
from .provenance import canonical_sha256
from .red_integrated_play import observed_cost


@dataclass(frozen=True)
class RecordedSequenceProjection:
    choices: tuple[MeasuredSequenceStep, ...]
    previews: tuple[SequencePreview, ...]
    initial_quests: tuple[str, ...]
    support_steps: int
    leading_support_actions: int
    leading_support_frames: int
    leading_support_debits: int
    leading_support_credits: int
    leading_support_reported_losses: int
    leading_support_quests: tuple[str, ...]
    story_contexts: tuple[str | None, ...]
    source_sha256: str
    plan_sha256: str
    selected_kinds: tuple[str, ...]
    native_verification_required: bool = True
    training_eligible: bool = False
    loss_accounting_complete: bool = False
    executor_ownership_verified: bool = False


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("sequence receipt must be an object")
    return value


def _quests(value: Any) -> tuple[str, ...]:
    if (
        not isinstance(value, list) or any(type(v) is not str or not v for v in value)
        or len(value) != len(set(value))
    ):
        raise ValueError("sequence objective facts differ")
    return tuple(sorted(value))


def read_sequence_receipts(
    root: Path, *, expected_plan_sha256: str, expected_result_sha256: str,
    source_sha256: str,
) -> RecordedSequenceProjection:
    """Read every executed top-level step; never treat child logs as new choices.

    Support following a choice is attached to that choice. Leading support costs
    are retained separately and cannot acquire a fabricated sampled action.
    Reported losses are a lower bound: nested battle audits must supply full
    blackout coverage. Unknown future previews are left unknown, not reconstructed
    from the later outcome. Legacy exceptional/partial executions fail projection
    without editing or discarding their original records.
    """
    plan, result = _read(root / "plan.json"), _read(root / "result.json")
    if (
        canonical_sha256(plan) != expected_plan_sha256
        or canonical_sha256(result) != expected_result_sha256
        or plan.get("schema") != "pokemon.red.autonomous-option-run.v1"
        or plan.get("continuous_player") is not True
        or plan.get("teacher_actions_allowed") is not False
        or result.get("model_sha256") != plan.get("model_sha256")
        or result.get("continuous_player") is not True
        or type(result.get("teacher_actions")) is not int or result["teacher_actions"] != 0
    ):
        raise ValueError("sequence run declaration differs")
    count = result.get("executed_decisions")
    if type(count) is not int or not 1 <= count <= 10:
        raise ValueError("sequence executed census differs")
    folders = tuple(root / f"step-{i:03d}" for i in range(count))
    if {p.parent for p in root.glob("step-*/outcome.json")} != set(folders):
        raise ValueError("sequence outcome census differs")
    if {p.parent for p in root.glob("step-*/execution-started.json")} != set(folders):
        raise ValueError("sequence contains an unaccounted started execution")
    rows = tuple(_read(folder / "outcome.json") for folder in folders)
    if result.get("outcomes") != list(rows):
        raise ValueError("sequence result omits or changes an outcome")
    projection = _project_rows(root, plan, rows, source_sha256, expected_plan_sha256)
    if (type(result.get("model_decisions")) is not int
        or type(result.get("support_decisions")) is not int
        or result.get("model_decisions") != len(projection.choices)
        or result.get("support_decisions") != projection.support_steps):
        raise ValueError("sequence model/support census differs")
    return projection


def read_sequence_prefix(
    root: Path, *, expected_plan_sha256: str, source_sha256: str,
    outcome_sha256: tuple[str, ...], boundary_sha256: str,
) -> RecordedSequenceProjection:
    """Read only a previously sealed prefix, never result.json or future steps.

    The live recorder supplies receipt hashes when each outcome is sealed, then
    binds the end to its current independently observed state. This grants no
    native verification or TRAIN admission beyond the closed-record projector.
    """
    plan = _read(root / "plan.json")
    if (
        canonical_sha256(plan) != expected_plan_sha256
        or plan.get("schema") != "pokemon.red.autonomous-option-run.v1"
        or plan.get("continuous_player") is not True
        or plan.get("teacher_actions_allowed") is not False
        or type(outcome_sha256) is not tuple or len(outcome_sha256) > 10
    ):
        raise ValueError("sequence prefix declaration differs")
    rows = tuple(_read(root / f"step-{i:03d}" / "outcome.json")
                 for i in range(len(outcome_sha256)))
    if any(canonical_sha256(row) != digest for row, digest in zip(
        rows, outcome_sha256, strict=True,
    )):
        raise ValueError("sequence prefix receipt changed")
    terminal = source_sha256 if not rows else rows[-1].get("terminal_state_sha256")
    if terminal != boundary_sha256:
        raise ValueError("sequence prefix does not reach current boundary")
    return _project_rows(root, plan, rows, source_sha256, expected_plan_sha256)


def _project_rows(
    root: Path, plan: dict[str, Any], rows: tuple[dict[str, Any], ...],
    source_sha256: str, expected_plan_sha256: str,
) -> RecordedSequenceProjection:
    folders = tuple(root / f"step-{i:03d}" for i in range(len(rows)))
    choices: list[MeasuredSequenceStep] = []
    previews: list[SequencePreview] = []
    contexts: list[str | None] = []
    kinds: list[str] = []
    leading = dict(actions=0, frames=0, debits=0, credits=0, losses=0)
    support_count = 0
    previous_sha = source_sha256
    previous_facts = None
    initial: tuple[str, ...] = ()
    leading_quests: tuple[str, ...] = ()
    for ordinal, (folder, row) in enumerate(zip(folders, rows, strict=True)):
        before = _read(folder / "before.json")
        intent = _read(folder / "intent.json")
        decision = _read(folder / "decision.json")
        execution = _read(folder / "execution-started.json")
        before_sha = sha256((folder / "before.state").read_bytes()).hexdigest()
        after_sha = sha256((folder / "terminal.state").read_bytes()).hexdigest()
        if (
            type(row.get("ordinal")) is not int or row["ordinal"] != ordinal
            or before_sha != previous_sha
            or before_sha != before.get("state_sha256")
            or before_sha != intent.get("state_sha256")
            or before_sha != execution.get("state_sha256")
            or before_sha != row.get("before_state_sha256")
            or after_sha != row.get("terminal_state_sha256")
            or before.get("facts") != row.get("before")
            or previous_facts is not None and previous_facts != row.get("before")
            or before.get("safe") is not True or row.get("safe_terminal") is not True
            or decision != row.get("choice")
            or intent.get("model_sha256") != plan["model_sha256"]
            or execution.get("selected_kind") != row.get("selected_kind")
            or any(row.get(k) is not None for k in ("error", "error_type", "error_chain"))
            or row.get("verification") not in {"succeeded", "failed"}
        ):
            raise ValueError("sequence step binding or completion differs")
        old, new = row["before"], row["after"]
        cost = observed_cost(old, new)
        if (
            cost is None or row.get("observed_cost") != cost
            or cost["actions"] != cost["completed_actions"] or cost["actions"] <= 0
            or row.get("measured_cost") != {k: cost[k] for k in ("actions", "frames", "cash_spent")}
        ):
            raise ValueError("sequence counter ownership differs")
        old_quests, new_quests = _quests(old.get("completed_objectives")), _quests(
            new.get("completed_objectives"),
        )
        if not set(old_quests) <= set(new_quests):
            raise ValueError("sequence lost prior quest progress")
        if ordinal == 0:
            initial = old_quests
        menu = intent.get("menu", {})
        if decision.get("menu_sha256") != execution.get("menu_sha256"):
            raise ValueError("sequence selected menu differs")
        mode = decision.get("mode")
        if menu.get("schema") == "pokemon.red.player-support.v1":
            expected_decision = {**menu, "menu_sha256": canonical_sha256(menu)}
            if decision != expected_decision or row.get("support_role") != menu.get("support_role"):
                raise ValueError("sequence support binding differs")
            learned = False
            preview = None
            index, candidate_count = 0, 1
        else:
            decoded = restore_living_dex_policy_menu(menu["menu"])
            if decoded.policy_sha256 != menu.get("menu_sha256") or (
                decoded.policy_sha256 != decision.get("menu_sha256")
                or decision.get("model_sha256") != plan["model_sha256"]
            ):
                raise ValueError("sequence policy menu differs")
            selected_index = decision.get("selected_candidate_index")
            if type(selected_index) is not int or selected_index not in decoded.available_indices:
                raise ValueError("sequence selected unavailable candidate")
            index = selected_index
            if mode not in {"model_exploration", "equivalent_exploration", "deterministic_safety"}:
                raise ValueError("sequence unknown choice authority")
            learned = mode == "model_exploration"
            if learned and row.get("support_role") is not None:
                raise ValueError("sequence learned choice mislabeled as support")
            # No future outcome is accepted as pre-choice knowledge.
            preview = SequencePreview((decoded.candidates[index].challenge, None, None, None), True)
            candidate_count = len(decoded.candidates)
        context = None
        private = intent.get("private_story_contexts")
        if private is not None:
            if (
                not isinstance(private, list) or len(private) != candidate_count
                or any(not isinstance(p, dict) or set(p) != {"binding_ref", "objective_ref"}
                       or type(p["binding_ref"]) is not str or not p["binding_ref"]
                       or (p["objective_ref"] is not None and (
                           type(p["objective_ref"]) is not str or not p["objective_ref"]
                       )) for p in private)
                or len({p["binding_ref"] for p in private}) != len(private)
                or private[index]["binding_ref"] != execution.get("selected_binding_ref")
            ):
                raise ValueError("sequence pre-choice story context differs")
            context = private[index]["objective_ref"]
            if context is not None and row.get("selected_kind") != "advance_story":
                raise ValueError("sequence story context belongs to a nonstory action")
        if row.get("learning_eligible") is not learned:
            raise ValueError("sequence learning authority differs")
        evidence = row.get("evidence") or {}
        battle = evidence.get("battle") or {}
        losses = int(battle.get("outcome") == "lost")
        debit, credit = max(0, cost["cash_spent"]), max(0, -cost["cash_spent"])
        if learned:
            assert preview is not None
            if not choices:
                # Leading support is observed, but not caused by this first choice.
                initial = old_quests
            choices.append(MeasuredSequenceStep(
                # Bound pre-input intent+choice, not a hash containing future outcomes.
                canonical_sha256({"intent": intent, "decision": decision}), plan["model_sha256"],
                before_sha, after_sha, cost["actions"], cost["frames"], debit, losses,
                quests=new_quests, cash_credits=credit,
            ))
            previews.append(preview)
            contexts.append(context)
            kinds.append(row["selected_kind"])
        else:
            support_count += 1
            if choices:
                prior = choices[-1]
                choices[-1] = replace(
                    prior, after_sha256=after_sha, actions=prior.actions + cost["actions"],
                    frames=prior.frames + cost["frames"], cash_debits=prior.cash_debits + debit,
                    cash_credits=prior.cash_credits + credit, blackouts=prior.blackouts + losses,
                    quests=new_quests,
                )
            else:
                for name, value in zip(leading, (
                    cost["actions"], cost["frames"], debit, credit, losses,
                ), strict=True):
                    leading[name] += value
                leading_quests = new_quests
        previous_sha, previous_facts = after_sha, new
    return RecordedSequenceProjection(
        tuple(choices), tuple(previews), initial, support_count,
        leading["actions"], leading["frames"], leading["debits"], leading["credits"],
        leading["losses"], leading_quests, tuple(contexts), source_sha256,
        expected_plan_sha256, tuple(kinds),
    )
