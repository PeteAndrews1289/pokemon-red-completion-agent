"""Outcome-ranked trust-region corrections with exact retained-budget admission.

Local worse-choice guards are conservative. Failure under these guards does not
prove infeasibility of the original numeric budgets or of the neural model.
"""

from dataclasses import replace
from time import monotonic

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, hstack, vstack

from .red_trainer_budgeted_fit import selected_regret, unique_budget_replay
from .red_trainer_ranking_diagnostics import score_jacobian
from .red_trainer_retention import _batch, _forward, batch_loss_gradient


def ranking_guards(model, cases):
    """Protect against strictly worse returns, allowing old mistakes to improve."""
    x, mask, regret = _batch(cases)
    hidden, scores, _ = _forward(x, mask, model.weights1, model.bias1, model.weights2)
    rows, lower, labels = [], [], []
    for i, winner in enumerate(scores.argmax(axis=1)):
        for other in range(len(cases[i].candidate_vectors)):
            if regret[i, other] <= regret[i, winner]:
                continue
            dw = model.weights2 * (1 - hidden[i, winner] ** 2)
            do = model.weights2 * (1 - hidden[i, other] ** 2)
            rows.append(
                np.concatenate(
                    (
                        (np.outer(x[i, winner], dw) - np.outer(x[i, other], do)).ravel(),
                        dw - do,
                        hidden[i, winner] - hidden[i, other],
                    )
                )
            )
            margin = float(scores[i, winner] - scores[i, other])
            lower.append(min(0.05, max(0.0, margin) * 0.5) - margin)
            labels.append((i, int(winner), other))
    width = model.weights1.size + model.bias1.size + model.weights2.size
    return np.asarray(rows).reshape((-1, width)), np.asarray(lower), labels


def solve_direction(jacobian, matrix, lower, radius, needed):
    """Maximize one useful margin jointly, then choose a smaller L1 direction."""
    j = np.asarray(jacobian, dtype=float)
    a = np.asarray(matrix, dtype=float)
    b = np.asarray(lower, dtype=float)
    if (
        j.ndim != 1
        or a.shape != (len(b), len(j))
        or not np.all(np.isfinite(j))
        or not np.all(np.isfinite(a))
        or not np.all(np.isfinite(b))
        or not np.isfinite(radius)
        or radius <= 0
        or not np.isfinite(needed)
        or needed <= 0
    ):
        raise ValueError("invalid ranking direction inputs")
    options = dict(
        maxiter=10000,
        time_limit=5.0,
        primal_feasibility_tolerance=1e-9,
        dual_feasibility_tolerance=1e-9,
    )
    first = linprog(
        -j, A_ub=csr_matrix(-a), b_ub=-b, bounds=(-radius, radius), method="highs", options=options
    )
    record = dict(
        status=int(first.status),
        message=str(first.message),
        iterations=int(first.nit),
        local_only=True,
    )
    if not first.success:
        return None, record
    maximum = float(j @ first.x)
    record["maximum_linear_gain"] = maximum
    if maximum <= 1e-9:
        record["reason"] = "no_useful_local_direction"
        return None, record
    required = 0.9 * min(maximum, needed)
    n = len(j)
    # d = positive - negative gives the same bounded minimum-L1 problem
    # without two epigraph inequalities per neural parameter. Cancellation
    # cannot improve this objective and is unnecessary for any feasible d.
    constraints = vstack(
        (
            hstack((csr_matrix(-a), csr_matrix(a))),
            hstack((csr_matrix(-j.reshape(1, -1)), csr_matrix(j.reshape(1, -1)))),
        ),
        format="csr",
    )
    second = linprog(
        np.ones(2 * n),
        A_ub=constraints,
        b_ub=np.r_[-b, -required],
        bounds=(0, radius),
        method="highs",
        options=options,
    )
    record.update(
        minimum_step_status=int(second.status),
        minimum_step_message=str(second.message),
        minimum_step_iterations=int(second.nit),
        required_gain=required,
    )
    if not second.success:
        record["reason"] = "minimum_step_solver_failure"
        return None, record
    step = second.x[:n] - second.x[n:]
    slack = a @ step - b
    violation = max(
        0.0,
        float(np.max(-slack, initial=0)),
        required - float(j @ step),
        float(np.max(np.abs(step))) - radius,
    )
    record.update(
        linear_violation=violation,
        predicted_gain=float(j @ step),
        binding_rows=np.flatnonzero(slack <= 1e-7).tolist(),
        displacement_l1=float(np.abs(step).sum()),
        radius=float(radius),
    )
    if not np.all(np.isfinite(step)) or violation > 1e-7:
        record["reason"] = "linear_residual_failure"
        return None, record
    return step, record


def solve_curvature_direction(jacobian, matrix, lower, radius, needed, actual_change):
    """Correct measured linearization error, never relaxing the original rows.

    The callback evaluates the same frozen winner/other score differences in
    the trial network. Four local solves are a fixed bound, not a fit sweep.
    Exact nonlinear budgets still decide admission in the caller.
    """
    base = np.asarray(lower)
    tightened = base.copy()
    rounds = []
    for _ in range(4):
        step, solver = solve_direction(jacobian, matrix, tightened, radius, needed)
        row = dict(solver=solver, tightened_rows=np.flatnonzero(tightened > base).tolist())
        rounds.append(row)
        if step is None:
            return None, {**solver, "curvature_rounds": rounds}
        actual = np.asarray(actual_change(step))
        if actual.shape != base.shape or not np.all(np.isfinite(actual)):
            raise ValueError("invalid nonlinear guard changes")
        predicted = matrix @ step
        violation = np.maximum(base - actual, 0)
        row["nonlinear_guard_violation"] = float(np.max(violation, initial=0))
        if np.max(violation, initial=0) <= 1e-9:
            return step, {**solver, "curvature_rounds": rounds}
        # Account for curvature using this trial's measured prediction error.
        # Tightening is monotonic during a correction; original rows stay fixed.
        correction = 1.25 * np.maximum(predicted - actual, 0) + 1e-8
        tightened = np.maximum(tightened, np.where(violation > 1e-9, base + correction, base))
    return step, {**solver, "curvature_rounds": rounds}


def fit_joint_ranking(
    initial,
    terminal,
    anchors,
    budgets,
    *,
    replay,
    epochs,
    learning_rate,
    objective,
    retention_replay,
    curvature_correction=False,
    allow_initial_infeasibility=False,
):
    """One bounded cyclic trajectory, with every accepted checkpoint retained."""
    start = monotonic()
    size, width = initial.weights1.size, initial.bias1.size

    def pack(m):
        return np.concatenate((m.weights1.ravel(), m.bias1, m.weights2))

    def unpack(p):
        return replace(
            initial,
            weights1=p[:size].reshape(initial.weights1.shape),
            bias1=p[size : size + width],
            weights2=p[size + width :],
            training_objective=objective,
        )

    def measured(m):
        return {b.name: selected_regret(m, b.cases) + b.offset for b in budgets}

    def feasible(values):
        return all(values[b.name] <= b.maximum for b in budgets)

    guards = unique_budget_replay(terminal, budgets)
    current, best = initial, None
    best_key = (float("inf"), float("inf"))
    history, steps, checkpoints = [], [], []
    best_epoch = None
    stop = "attempt_limit"

    def checkpoint():
        nonlocal best, best_key, best_epoch
        values = measured(current)
        key = (selected_regret(current, terminal), batch_loss_gradient(current, terminal)[0])
        admitted = feasible(values)
        epoch = len(history)
        improved = admitted and key < best_key
        if improved:
            best, best_key, best_epoch = current, key, epoch
        history.append(
            dict(
                epoch=epoch,
                budgets=values,
                feasible=admitted,
                selected=improved,
                terminal_selected_regret=key[0],
                terminal_expected_regret=key[1],
            )
        )
        checkpoints.append(dict(epoch=epoch, parameters=pack(current).tolist()))

    checkpoint()
    if not history[0]["feasible"] and not allow_initial_infeasibility:
        stop = "initial_budget_infeasible"
    else:
        while len(steps) < epochs:
            accepted_in_sweep = 0
            incorrect = 0
            for case_index, case in enumerate(terminal):
                for _ in range(40):
                    if len(steps) >= epochs or monotonic() - start >= 1800:
                        break
                    scores = np.asarray(current.scores(case.candidate_vectors))
                    chosen = int(scores.argmax())
                    returns = np.asarray(case.mean_returns)
                    if returns[chosen] == returns.max():
                        break
                    incorrect += 1
                    target = int(np.argmax(np.where(returns == returns.max(), scores, -np.inf)))
                    margin = float(scores[target] - scores[chosen])
                    jac = score_jacobian(current, case.candidate_vectors[target]) - score_jacobian(
                        current, case.candidate_vectors[chosen]
                    )
                    matrix, lower, labels = ranking_guards(current, guards)
                    if curvature_correction:
                        guard_x, guard_mask, _ = _batch(guards)
                        _, guard_scores, _ = _forward(
                            guard_x, guard_mask, current.weights1, current.bias1, current.weights2
                        )
                        indices = np.asarray(labels, dtype=int).reshape((-1, 3))
                        before_margins = (
                            guard_scores[indices[:, 0], indices[:, 1]]
                            - guard_scores[indices[:, 0], indices[:, 2]]
                        )

                        guard_parameters = pack(current)

                        def actual_change(
                            delta,
                            parameters=guard_parameters,
                            x=guard_x,
                            mask=guard_mask,
                            ix=indices,
                            margins=before_margins,
                        ):
                            trial = unpack(parameters + delta)
                            _, trial_scores, _ = _forward(
                                x, mask, trial.weights1, trial.bias1, trial.weights2
                            )
                            return (
                                trial_scores[ix[:, 0], ix[:, 1]]
                                - trial_scores[ix[:, 0], ix[:, 2]]
                                - margins
                            )

                    attempts = []
                    accepted = False
                    before_regret = selected_regret(current, terminal)
                    before_values = measured(current)
                    restoring = allow_initial_infeasibility and not feasible(before_values)
                    for shrink in range(8):
                        if monotonic() - start >= 1800:
                            break
                        args = (jac, matrix, lower, learning_rate * 0.5**shrink, 0.1 - margin)
                        step, solver = (
                            solve_curvature_direction(*args, actual_change)
                            if curvature_correction
                            else solve_direction(*args)
                        )
                        row = dict(shrink=shrink, solver=solver, accepted=False)
                        attempts.append(row)
                        if step is None:
                            if curvature_correction:
                                continue
                            break
                        candidate = unpack(pack(current) + step)
                        values = measured(candidate)
                        cs = candidate.scores(case.candidate_vectors)
                        new_margin = float(cs[target] - cs[chosen])
                        fresh_regret = selected_regret(candidate, terminal)
                        accepted = (
                            (
                                feasible(values)
                                or (restoring and all(
                                    max(0.0, values[b.name] - b.maximum)
                                    <= max(0.0, before_values[b.name] - b.maximum)
                                    for b in budgets
                                ))
                            )
                            and fresh_regret <= before_regret + 1e-12
                            and new_margin > margin + 1e-9
                        )
                        row.update(
                            accepted=bool(accepted),
                            private_feasibility_recovery=bool(restoring and not feasible(values)),
                            margin=new_margin,
                            fresh_regret=fresh_regret,
                            violated=[b.name for b in budgets if values[b.name] > b.maximum],
                        )
                        if accepted:
                            current = candidate
                            accepted_in_sweep += 1
                            checkpoint()
                            break
                    steps.append(
                        dict(
                            attempt=len(steps) + 1,
                            case_index=case_index,
                            chosen=chosen,
                            target=target,
                            margin_before=margin,
                            accepted=bool(accepted),
                            guard_labels=labels,
                            attempts=attempts,
                        )
                    )
                    if not accepted:
                        break
                if len(steps) >= epochs or monotonic() - start >= 1800:
                    break
            if monotonic() - start >= 1800:
                stop = "time_limit"
                break
            if incorrect == 0:
                stop = "all_fresh_choices_optimal"
                break
            if accepted_in_sweep == 0:
                stop = "no_accepted_local_correction"
                break
    receipt = dict(
        update_rule=("joint_ranking_curvature_v1" if curvature_correction else "joint_ranking_v1"),
        objective=objective,
        epochs=epochs,
        learning_rate=learning_rate,
        initial_feasible=history[0]["feasible"],
        allow_initial_infeasibility=allow_initial_infeasibility,
        private_infeasible_checkpoints=sum(not h["feasible"] for h in history),
        feasible_checkpoints=sum(h["feasible"] for h in history),
        selected_epoch=best_epoch,
        initial_selected_regret=history[0]["terminal_selected_regret"],
        final_selected_regret=None if best is None else best_key[0],
        initial_expected_regret=history[0]["terminal_expected_regret"],
        final_expected_regret=None if best is None else best_key[1],
        accepted_steps=len(history) - 1,
        stop_reason=stop,
        steps=steps,
        history=history,
        checkpoints=checkpoints,
        seconds=monotonic() - start,
        guard_scope="conservative local worse-choice margins; not global infeasibility",
        retention_replay=dict(
            mode=retention_replay,
            anchor_cases=len(anchors),
            budget_cases=sum(len(b.cases) for b in budgets),
            unique_replay_cases=len(replay),
            role="constraints, not shared gradient",
        ),
    )
    return best, receipt
