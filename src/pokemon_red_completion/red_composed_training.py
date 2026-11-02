"""Measured proposal tables make cross-head retention an exact training constraint.

Tables contain only already measured first-action returns. They do not simulate
unexecuted outcomes, alter inference, or assume an ideal downstream controller.
"""

from dataclasses import dataclass, replace
from statistics import fmean

from .red_battle_catalog import PokemonRedBattleCatalog
from .red_status_battle_features import project_for_head, status_choice_slots
from .red_switch_control_examples import _inventory, build_switch_control_examples
from .red_trainer_budgeted_fit import RegretBudget, fit_budgeted_head, selected_regret
from .red_trainer_practice_features import project_trainer_switch_features
from .red_trainer_practice_fit import _legacy_batch, _observed_returns, _tied_values
from .red_trainer_practice_head import TrainerHeadExample
from .red_trainer_proposed_control import proposed_control


@dataclass(frozen=True)
class ControlProposalTable:
    switch_vectors: tuple[tuple[float, ...], ...]
    control_pairs: tuple[TrainerHeadExample, ...]
    best_full_return: float


@dataclass(frozen=True)
class ComposedSwitchInventory:
    cases: tuple[TrainerHeadExample, ...]
    offset: float
    control_contexts: int

    def regret(self, switch):
        return (selected_regret(switch, self.cases) if self.cases else 0.0) + self.offset


def control_proposal_tables(targets, model, *, catalog=None):
    """Validate TRAIN admission, then enumerate existing measured proposal pairs."""
    targets = tuple(targets)
    catalog = catalog or PokemonRedBattleCatalog()
    build_switch_control_examples(targets, model, catalog=catalog)
    tables = []
    for target in targets:
        head = target["heads"].get("control")
        if head is None:
            continue
        refs = head["choice_refs"]
        moves, switches, decline = _inventory(refs)
        observed = _observed_returns("control", refs, head["returns"], head.get("timing_returns"))
        full = tuple(fmean(r[i] for r in observed) for i in range(len(refs)))
        observation = target["observation"]
        base = _legacy_batch(target.get("legacy_model_input"))
        if moves and model.damage_reference is not None:
            projected = project_for_head(observation, base, model.move)
            moves = status_choice_slots(projected, moves, model.damage_reference)
        projected_switches = project_trainer_switch_features(observation, catalog)
        vectors = tuple(
            projected_switches.candidate_vectors[projected_switches.candidate_slots.index(slot)]
            for slot in switches
        )
        pairs = []
        for slot in switches:
            proposal = proposed_control(
                observation,
                catalog=catalog,
                move_head=model.move,
                switch_head=model.switch,
                move_batch=None if decline else base,
                move_slots=moves,
                switch_slots=(slot,),
            )
            selected_refs = (
                "pokemon.core:battle:decline-switch"
                if decline
                else f"pokemon.core:battle:move:{proposal.move_slot}",
                f"pokemon.core:battle:switch:{slot}",
            )
            means = tuple(full[refs.index(ref)] for ref in selected_refs)
            pairs.append(
                TrainerHeadExample(
                    proposal.candidate_vectors, _tied_values(means), mean_returns=means
                )
            )
        tables.append(ControlProposalTable(vectors, tuple(pairs), max(full)))
    return tuple(tables)


def composed_switch_inventory(tables, control):
    """Exact actual control regret as a function of switch weights, including offsets.

    Singleton contexts cannot be optimized by switch but still count in the mean.
    Variable examples are scaled so their mean plus offset has the original group
    denominator. Never drop their constant cost or use an optimistic control choice.
    """
    tables = tuple(tables)
    if not tables:
        return ComposedSwitchInventory((), 0.0, 0)
    count = sum(len(t.switch_vectors) > 1 for t in tables)
    scale = count / len(tables)
    rows, constants = [], []
    for table in tables:
        values = tuple(
            pair.mean_returns[control.predict_index(pair.candidate_vectors)]
            for pair in table.control_pairs
        )
        if len(values) != len(table.switch_vectors) or not values:
            raise ValueError("composed proposal inventory differs")
        constants.append(table.best_full_return - max(values))
        if len(values) > 1:
            scaled = tuple(v * scale for v in values)
            rows.append(
                TrainerHeadExample(table.switch_vectors, _tied_values(scaled), mean_returns=scaled)
            )
    return ComposedSwitchInventory(tuple(rows), fmean(constants), len(tables))


def whole_metrics(model, targets):
    from .red_switch_control_curriculum import control_proposal_regret_offset

    rows = build_switch_control_examples(targets, model)
    return {
        head: dict(
            cases=len(cases),
            regret=selected_regret(getattr(model, head), tuple(cases))
            + (control_proposal_regret_offset(targets, cases) if head == "control" else 0),
        )
        for head, cases in rows.items()
        if cases
    }


def composed_stage_inputs(
    parent, current, targets, retained, stage, *, tolerance=1e-10, tables=None
):
    """Expose auditable fixed examples/budgets for each stage of the single fit."""
    from .red_switch_control_curriculum import control_proposal_regret_offset

    if stage not in ("control_coverage", "composed_switch", "control_finish"):
        raise ValueError("unknown composed training stage")
    tables = tables or {
        name: control_proposal_tables(rows, parent)
        for name, rows in {"new": targets, **retained}.items()
    }
    before = {name: whole_metrics(parent, rows) for name, rows in retained.items()}
    rows = {name: build_switch_control_examples(v, current) for name, v in retained.items()}
    fresh = build_switch_control_examples(targets, current)
    budgets = []
    if stage != "composed_switch":
        terminal = (
            tuple(pair for t in tables["new"] for pair in t.control_pairs)
            if stage == "control_coverage"
            else tuple(fresh["control"])
        )
        for name, group in rows.items():
            if group["control"]:
                budgets.append(
                    RegretBudget(
                        name,
                        tuple(group["control"]),
                        before[name]["control"]["regret"] + tolerance,
                        control_proposal_regret_offset(retained[name], group["control"]),
                    )
                )
        return "control", terminal, tuple(rows["anchors"]["control"]), tuple(budgets)
    for name, group in rows.items():
        if group["switch"]:
            budgets.append(
                RegretBudget(
                    "switch/" + name,
                    tuple(group["switch"]),
                    before[name]["switch"]["regret"] + tolerance,
                )
            )
        if tables[name]:
            inventory = composed_switch_inventory(tables[name], current.control)
            maximum = before[name]["control"]["regret"] + tolerance
            if inventory.cases:
                budgets.append(
                    RegretBudget("control/" + name, inventory.cases, maximum, inventory.offset)
                )
            elif inventory.offset > maximum:
                raise ValueError("immutable control proposal cost exceeds retained budget")
    if fresh["switch"]:
        budgets.append(
            RegretBudget(
                "fresh-switch",
                tuple(fresh["switch"]),
                whole_metrics(parent, targets)["switch"]["regret"] + tolerance,
            )
        )
    new = composed_switch_inventory(tables["new"], current.control)
    if not new.cases:
        raise ValueError("no variable fresh control proposals for composed switch learning")
    return "switch", new.cases, tuple(rows["anchors"]["switch"]), tuple(budgets)


def fit_composed_once(
    parent,
    targets,
    retained,
    *,
    epochs=600,
    learning_rate=0.05,
    stage_sink=None,
    switch_update_rule="joint_ranking_v1",
):
    """Coverage, composed reserve learning, then control; unchanged final gates."""
    if not retained or "anchors" not in retained or any(not v for v in retained.values()):
        raise ValueError("complete retained groups required")
    if "new" in retained:
        raise ValueError("reserved group name")
    if switch_update_rule not in {"joint_ranking_v1", "joint_ranking_curvature_v1"}:
        raise ValueError("unknown composed switch update rule")
    current = parent
    tables = {
        name: control_proposal_tables(rows, parent)
        for name, rows in {"new": targets, **retained}.items()
    }
    report = dict(fits=1, method="composed_ranking_v1", stages={}, retention={})
    for stage in ("control_coverage", "composed_switch", "control_finish"):
        head, terminal, anchors, budgets = composed_stage_inputs(
            parent, current, targets, retained, stage, tables=tables
        )
        fitted, receipt = fit_budgeted_head(
            getattr(current, head),
            terminal,
            anchors,
            budgets,
            epochs=epochs,
            learning_rate=learning_rate,
            objective="pairwise_regret",
            retention_replay="unique_budget_cases_v1",
            update_rule=switch_update_rule if head == "switch" else "joint_ranking_v1",
        )
        report["stages"][stage] = dict(head=head, fit=receipt)
        if stage_sink is not None:
            stage_sink(
                stage, None if fitted is None else replace(current, **{head: fitted}), receipt
            )
        if fitted is None:
            return None, {**report, "passed": False, "reason": "no feasible composed checkpoint"}
        current = replace(current, **{head: fitted})
    for name, records in {"new": targets, **retained}.items():
        before, after = whole_metrics(parent, records), whole_metrics(current, records)
        metrics = {
            h: dict(before=before[h]["regret"], after=m["regret"], cases=m["cases"])
            for h, m in after.items()
        }
        if name == "new":
            report["new"] = metrics
        else:
            report["retention"][name] = metrics
    regressions = sum(
        v["after"] > v["before"] + 1e-10 for g in report["retention"].values() for v in g.values()
    )
    unchanged = all(
        current.to_dict()[k] == parent.to_dict()[k] for k in ("move", "damage_reference")
    )
    s, c = report["new"]["switch"], report["new"]["control"]
    report.update(
        retention_regressions=regressions,
        damage_status_unchanged=unchanged,
        passed=bool(
            unchanged
            and not regressions
            and s["after"] <= s["before"] + 1e-10
            and c["before"] > 1e-10
            and c["after"] <= 0.9 * c["before"]
        ),
    )
    return replace(
        current,
        train_capture_ids=tuple(
            sorted(set(current.train_capture_ids) | {v["capture_id"] for v in targets})
        ),
    ), report
