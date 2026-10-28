"""Prospective native-state selection and one retained switch/control update.

Selection uses observed phase/resources, never the eventual battle result.
Callers authenticate TRAIN inputs and freeze all collection/optimizer budgets.
"""

from collections import Counter
from dataclasses import replace
from statistics import fmean

from .red_switch_control_examples import build_switch_control_examples
from .red_trainer_budgeted_fit import RegretBudget, fit_budgeted_head, selected_regret
from .red_trainer_practice_fit import _observed_returns

FAMILIES = (
    "useful_active_immune_reserve",
    "immune_active_covered_reserve",
    "fragile_fast_durable_slow",
    "status_attrition",
    "forced_replacement",
    "optional_prompt",
)


def capture_matches(family, event, *, faint_count=0):
    """First matching boundary; None explicitly permits any optional-prompt bucket.

    The default and forced-replacement strata stay exact. Callers must declare
    this TRAIN selection rule before collecting, not relabel an old trajectory.
    """
    any_prompt_bucket = family == "optional_prompt" and faint_count is None
    if family not in FAMILIES or (not any_prompt_bucket and (
        type(faint_count) is not int or not 0 <= faint_count <= 2
    )):
        raise ValueError("unknown curriculum family or faint bucket")
    if event.get("event") != "decision_started":
        return False
    state = event.get("state_before", {})
    hp = state.get("party_hp", [])
    if not hp or (not any_prompt_bucket and min(2, sum(v == 0 for v in hp)) != faint_count):
        return False
    mode = event.get("mode")
    if family == "forced_replacement":
        return mode == "forced_switch" and len(event.get("legal_party_slots", [])) >= 2
    if family == "optional_prompt":
        return mode == "switch_prompt" and bool(event.get("legal_party_slots"))
    if family == "status_attrition":
        return (
            mode == "main"
            and event.get("decision_index", 0) >= 2
            and bool(any(state.get("party_status") or []))
        )
    return mode == "main" and event.get("decision_index") == 1


def later_state_capture_matches(event, *, phase, minimum_faints=1):
    """Prospective TRAIN boundary after attrition, independent of eventual returns.

    This only selects a state to measure. It grants no actor action or label and
    does not relax the existing curriculum's exact faint buckets.
    """
    if phase not in ("main", "forced_switch") or (
        type(minimum_faints) is not int or not 1 <= minimum_faints <= 4
    ):
        raise ValueError("unknown later-state phase or faint minimum")
    if event.get("event") != "decision_started" or event.get("mode") != phase:
        return False
    hp = event.get("state_before", {}).get("party_hp", [])
    if (
        not hp
        or any(type(value) is not int or value < 0 for value in hp)
        or sum(value == 0 for value in hp) < minimum_faints
        or sum(value > 0 for value in hp) < 2
    ):
        return False
    if phase == "forced_switch":
        slots = event.get("legal_party_slots", [])
        return (
            len(slots) >= 2
            and all(type(slot) is int and 1 <= slot <= len(hp) for slot in slots)
            and len(set(slots)) == len(slots)
            and all(hp[slot - 1] > 0 for slot in slots)
        )
    return True


def control_proposal_regret_offset(targets, examples):
    """Cost of actions excluded by the child proposals, in measured return units.

    Conditional regret within the two proposals alone can reward a worse proposal.
    Add this fixed offset when comparing models with different child proposals.
    """
    targets = [t for t in targets if "control" in t["heads"]]
    if len(targets) != len(examples) or not targets:
        raise ValueError("control regret inventory differs")
    gaps = []
    for target, example in zip(targets, examples, strict=True):
        head = target["heads"]["control"]
        observed = _observed_returns(
            "control", head["choice_refs"], head["returns"], head.get("timing_returns")
        )
        full = tuple(fmean(r[i] for r in observed) for i in range(len(head["choice_refs"])))
        gaps.append(max(full) - max(example.mean_returns))
    return fmean(gaps)


def fit_switch_control_once(
    model, targets, retained, *, epochs, learning_rate, tolerance=1e-10,
    retention_replay="anchors",
    update_rule="adam",
):
    """One two-stage trajectory; child proposals rebuilt before control fitting.

    Every retained group keeps its original mean-regret budget. Damage/status and
    their metadata remain byte-equivalent. No fitting/evaluation retry lives here.
    """
    if not retained or any(not rows for rows in retained.values()):
        raise ValueError("complete retained groups required")
    if retention_replay not in {"anchors", "unique_budget_cases_v1"}:
        raise ValueError("unknown retention replay mode")
    if update_rule not in {"adam", "projected_budget_v1", "joint_ranking_v1"}:
        raise ValueError("unknown budgeted update rule")
    original = model.to_dict()
    before = {name: build_switch_control_examples(rows, model) for name, rows in retained.items()}
    fresh = build_switch_control_examples(targets, model)
    report = {"fits": 1, "stages": {}, "retention": {}}
    if retention_replay != "anchors":
        report["retention_replay"] = retention_replay
    if update_rule != "adam":
        report["update_rule"] = update_rule
    current = model
    for head in ("switch", "control"):
        # Recompute every control row against the new concrete switch proposal.
        groups = {
            name: build_switch_control_examples(rows, current) for name, rows in retained.items()
        }
        new = build_switch_control_examples(targets, current)
        budgets = tuple(
            RegretBudget(
                name,
                tuple(rows[head]),
                selected_regret(getattr(model, head), tuple(before[name][head]))
                + (
                    control_proposal_regret_offset(retained[name], before[name][head])
                    if head == "control"
                    else 0.0
                )
                + tolerance,
                offset=(
                    control_proposal_regret_offset(retained[name], rows[head])
                    if head == "control"
                    else 0.0
                ),
            )
            for name, rows in groups.items()
            if rows[head]
        )
        anchors = tuple(groups["anchors"][head])
        fitted, receipt = fit_budgeted_head(
            getattr(current, head),
            tuple(new[head]),
            anchors,
            budgets,
            epochs=epochs,
            learning_rate=learning_rate,
            objective="pairwise_regret",
            **({"retention_replay": retention_replay} if retention_replay != "anchors" else {}),
            **({"update_rule": update_rule} if update_rule != "adam" else {}),
        )
        report["stages"][head] = receipt
        if fitted is None:
            return None, {**report, "passed": False, "reason": "no feasible retained checkpoint"}
        current = replace(current, **{head: fitted})
    after = build_switch_control_examples(targets, current)
    regressions = 0
    for name, rows in retained.items():
        examples = build_switch_control_examples(rows, current)
        metrics = {}
        for head in ("switch", "control"):
            if examples[head]:
                b = selected_regret(getattr(model, head), tuple(before[name][head]))
                c = selected_regret(getattr(current, head), tuple(examples[head]))
                if head == "control":
                    b += control_proposal_regret_offset(rows, before[name][head])
                    c += control_proposal_regret_offset(rows, examples[head])
                metrics[head] = {"before": b, "after": c, "cases": len(examples[head])}
                regressions += c > b + tolerance
        report["retention"][name] = metrics
    report["new"] = {
        head: {
            "before": selected_regret(getattr(model, head), tuple(fresh[head]))
            + (control_proposal_regret_offset(targets, fresh[head]) if head == "control" else 0.0),
            "after": selected_regret(getattr(current, head), tuple(after[head]))
            + (control_proposal_regret_offset(targets, after[head]) if head == "control" else 0.0),
            "cases": len(after[head]),
        }
        for head in ("switch", "control")
    }
    unchanged = all(current.to_dict()[k] == original[k] for k in ("move", "damage_reference"))
    report.update(retention_regressions=int(regressions), damage_status_unchanged=unchanged)
    s, c = report["new"]["switch"], report["new"]["control"]
    report["passed"] = bool(
        unchanged
        and not regressions
        and s["after"] <= s["before"] + tolerance
        and c["before"] > tolerance
        and c["after"] <= 0.9 * c["before"]
    )
    current = replace(
        current,
        train_capture_ids=tuple(
            sorted(set(current.train_capture_ids) | {t["capture_id"] for t in targets})
        ),
    )
    return current, report


def summarize_switch_comparison(records):
    """Frozen24-team/three-timing screen, after independent event/choice audit.

    This pure summary does not authenticate native evidence or grant authority.
    Timing siblings are not independent roots. All losses and costs are retained.
    """
    cells = {}
    families = {}
    for row in records:
        key = (row["case"], row["offset"], row["actor"])
        if (
            key in cells
            or row["offset"] not in (0, 6, 12)
            or row["actor"] not in ("baseline", "candidate")
            or row["family"] not in FAMILIES
        ):
            raise ValueError("comparison identity differs")
        if row["case"] in families and families[row["case"]] != row["family"]:
            raise ValueError("comparison family changes between arms")
        families[row["case"]] = row["family"]
        if type(row["win"]) is not bool or row["stop"] not in ("battle_won", "party_defeated"):
            raise ValueError("comparison requires uncensored terminal outcomes")
        if row["win"] != (row["stop"] == "battle_won"):
            raise ValueError("comparison winner and terminal disagree")
        for field in (
            "decisions",
            "pp_spent",
            "invalid",
            "teacher_interventions",
            "type_immune_attacks",
            "zero_power_choices_with_covered_alternative",
        ):
            if type(row[field]) is not int or row[field] < 0:
                raise ValueError("comparison metric must be a nonnegative integer")
        if row["decisions"] < 1 or (
            row["type_immune_attacks"] + row["zero_power_choices_with_covered_alternative"]
            > row["decisions"]
        ):
            raise ValueError("comparison decision/risk counts differ")
        forced = row.get("forced_mechanics", 0)
        if (
            type(forced) is not int
            or not 0 <= forced < row["decisions"]
            or row["type_immune_attacks"] + row["zero_power_choices_with_covered_alternative"]
            > row["decisions"] - forced
        ):
            raise ValueError("comparison learned/forced counts differ")
        cells[key] = row
    expected = {
        (case, offset, actor)
        for case in families
        for offset in (0, 6, 12)
        for actor in ("baseline", "candidate")
    }
    if (
        len(families) != 24
        or Counter(families.values()) != {f: 4 for f in FAMILIES}
        or set(cells) != expected
    ):
        raise ValueError("comparison requires all144declared paired episodes")
    sums = {}
    for actor in ("baseline", "candidate"):
        rows = [r for r in cells.values() if r["actor"] == actor]
        sums[actor] = {
            key: sum(r[key] for r in rows)
            for key in (
                "win",
                "decisions",
                "pp_spent",
                "invalid",
                "teacher_interventions",
                "type_immune_attacks",
                "zero_power_choices_with_covered_alternative",
            )
        }
        learned_opportunities = sum(r["decisions"] - r.get("forced_mechanics", 0) for r in rows)
        if any("forced_mechanics" in r for r in rows):
            sums[actor]["forced_mechanics"] = sum(r.get("forced_mechanics", 0) for r in rows)
            sums[actor]["learned_decisions"] = learned_opportunities
        sums[actor]["risk_rate"] = (
            sums[actor]["type_immune_attacks"]
            + sums[actor]["zero_power_choices_with_covered_alternative"]
        ) / learned_opportunities
    common = [
        (cells[(c, o, "baseline")], cells[(c, o, "candidate")])
        for c in families
        for o in (0, 6, 12)
        if cells[(c, o, "baseline")]["win"] and cells[(c, o, "candidate")]["win"]
    ]
    costs = {
        key: {
            actor: sum(pair[i][key] for pair in common)
            for i, actor in enumerate(("baseline", "candidate"))
        }
        for key in ("decisions", "pp_spent")
    }
    b, c = sums["baseline"], sums["candidate"]
    gates = dict(
        wins_noninferior=c["win"] >= b["win"],
        common_win_costs_noninferior=bool(common)
        and all(v["candidate"] <= v["baseline"] for v in costs.values()),
        risk_improved=c["risk_rate"] < b["risk_rate"] if b["risk_rate"] else c["risk_rate"] == 0,
        zero_invalid_and_interventions=all(
            sums[a][k] == 0 for a in sums for k in ("invalid", "teacher_interventions")
        ),
    )
    return dict(
        passed=all(gates.values()),
        gates=gates,
        totals=sums,
        common_wins=len(common),
        common_win_costs=costs,
        constructed_teams=24,
        timing_pairs=72,
        independent_natural_roots=0,
        authority_promotions=0,
    )
