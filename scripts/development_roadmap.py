"""Generate the development infographic from a stable baseline and current evidence.

This is a documentation projection, not an experiment gate or a gameplay process.
Run with --write after updating status; the existing docs check detects stale output.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = "configs/development-roadmap-state.json"
SVG = "docs/assets/development-roadmap.svg"
MARKDOWN = "docs/development-roadmap.md"


def _read(root: Path, relative: str) -> dict:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("roadmap reference must be repository-relative")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("roadmap document must be an object")
    return value


def load_roadmap(root: Path = ROOT) -> tuple[dict, dict, dict, dict]:
    state = _read(root, STATE)
    baseline_id = state["baseline_id"]
    baselines = {
        "red-first-v1": "configs/development-roadmap-baseline-v1.json",
        "red-first-v2-registered": "configs/development-roadmap-baseline-v2.json",
        "red-first-v3-full-run": "configs/development-roadmap-baseline-v3.json",
        "red-first-v4-legitimate-native": "configs/development-roadmap-baseline-v4.json",
    }
    if baseline_id not in baselines:
        raise ValueError("new roadmap baseline requires explicit adoption in the renderer")
    baseline = _read(root, baselines[baseline_id])
    focus = _read(root, "configs/active-product-focus.json")
    lane = next(lane for lane in focus["lanes"] if lane["status"] == "active")
    latest = lane["latest_reorientation"]
    if (
        state["schema"] != "pokemon.development-roadmap-state.v1"
        or baseline["baseline_id"] != baseline_id
        or state["as_of_session"] != latest["session_id"]
        or not state["reviews"]
        or state["reviews"][-1]["session"] != state["as_of_session"]
    ):
        raise ValueError("roadmap session review is stale")
    ids = [stage["id"] for stage in baseline["stages"]]
    if len(ids) != len(set(ids)) or set(ids) != set(state["stages"]):
        raise ValueError("roadmap stage inventory differs")
    current = [key for key, row in state["stages"].items() if row["status"] == "current"]
    if current != [state["current_stage"]]:
        raise ValueError("roadmap requires exactly one current stage")
    for row in state["stages"].values():
        if row["status"] not in {"verified", "current", "planned", "blocked"}:
            raise ValueError("roadmap stage status differs")
        if row["status"] in {"verified", "current"} and not row["evidence"]:
            raise ValueError("roadmap status requires evidence")
        if row["evidence"]:
            _read(root, row["evidence"])
    if baseline_id in {"red-first-v3-full-run", "red-first-v4-legitimate-native"}:
        gate = state.get("red_completion_gate", {})
        criteria = (
            (
                "fresh_start",
                "model_directed_start_to_finish",
                "champion_and_hall_of_fame",
                "full_local_red_pokedex",
                "legitimate_external_dependencies_resolved",
            )
            if baseline_id == "red-first-v3-full-run"
            else (
                "fresh_start",
                "model_directed_start_to_finish",
                "champion_and_hall_of_fame",
                "declared_red_route_pokedex",
                "deferred_dependency_ledger_verified",
            )
        )
        if set(gate) != {*criteria, "evidence"} or any(
            type(gate.get(key)) is not bool for key in criteria
        ):
            raise ValueError("full Red completion gate is not explicit")
        passed = all(gate[key] for key in criteria)
        if any(gate[key] for key in criteria) and not gate["evidence"]:
            raise ValueError("full Red completion claims require evidence")
        if gate["evidence"]:
            _read(root, gate["evidence"])
        if not passed and any(
            state["stages"][key]["status"] in {"current", "verified"}
            for key in ("red-hack", "crystal", "cross-generation")
        ):
            raise ValueError("complete the full Red run and Pokedex before any ROM hack")
    items = state["milestone"]["items"]
    if not items or len({item["id"] for item in items}) != len(items):
        raise ValueError("roadmap checklist differs")
    for item in items:
        if type(item["done"]) is not bool or (item["done"] and not item["evidence"]):
            raise ValueError("completed checklist item requires evidence")
        if item["evidence"]:
            _read(root, item["evidence"])
    reference = _read(root, "configs/dashboard-learning-evidence.json")
    evidence = _read(root, reference["path"])
    if hashlib.sha256((root / reference["path"]).read_bytes()).hexdigest() != reference["sha256"]:
        raise ValueError("roadmap learning evidence changed")
    validate_progress(root, state)
    return baseline, state, lane, evidence



PROGRESS_RUBRICS = {"workstream-checklist-v1": "56c9f953b14480f60c38f42bc18a7060a8145cba2434a83e655f31cda070445e"}


def progress_rows(state: dict) -> list[dict]:
    """Derive checklist percentages and percentage-point deltas; never average workstreams."""
    tracking = state.get("workstream_progress")
    if tracking is None:
        return []  # Older archived roadmap documents have no invented baseline.
    latest = tracking["sessions"][-1]
    rows = []
    for workstream in tracking["workstreams"]:
        key = workstream["id"]
        total = len(workstream["criteria"])
        before = len(latest["before"][key])
        after = len(latest["after"][key])
        rows.append(dict(id=key, title=workstream["title"], total=total, done=after,
                         before=100 * before / total, percent=100 * after / total,
                         delta=100 * (after - before) / total))
    return rows


def validate_progress(root: Path, state: dict) -> None:
    tracking = state.get("workstream_progress")
    if tracking is None:
        return
    workstreams = tracking["workstreams"]
    rubric = [dict(id=w["id"], title=w["title"], criteria=[
        {k: c[k] for k in ("id", "label", "group")} for c in w["criteria"]
    ]) for w in workstreams]
    digest = hashlib.sha256(json.dumps(rubric, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if (PROGRESS_RUBRICS.get(tracking["rubric_version"]) != digest
            or tracking["rubric_sha256"] != digest):
        raise ValueError("progress denominator changed; explicitly version and rebaseline the rubric")
    inventory = {w["id"]: {c["id"] for c in w["criteria"]} for w in workstreams}
    for w in workstreams:
        if not w["criteria"] or len(inventory[w["id"]]) != len(w["criteria"]):
            raise ValueError("progress criterion inventory differs")
        for criterion in w["criteria"]:
            evidence = criterion["evidence"]
            if type(criterion["done"]) is not bool or (criterion["done"] and not evidence):
                raise ValueError("progress credit requires evidence")
            if evidence:
                _read(root, evidence["path"])
                if hashlib.sha256((root / evidence["path"]).read_bytes()).hexdigest() != evidence["sha256"]:
                    raise ValueError("progress evidence changed")
    previous = None
    sessions = tracking["sessions"]
    if (not sessions or sessions[0]["session"] != tracking["baseline_session"]
            or sessions[-1]["session"] != state["as_of_session"]
            or len({s["session"] for s in sessions}) != len(sessions)):
        raise ValueError("progress session history is stale")
    for index, session in enumerate(sessions):
        for key in ("before", "after"):
            snapshot = session[key]
            if set(snapshot) != set(inventory) or any(
                len(values) != len(set(values)) or not set(values) <= inventory[k]
                for k, values in snapshot.items()
            ):
                raise ValueError("progress snapshot differs from rubric")
        if index == 0:
            if session["kind"] != "baseline" or session["before"] != session["after"]:
                raise ValueError("progress baseline cannot invent a session gain")
        elif session["kind"] != "session" or session["before"] != previous:
            raise ValueError("progress history must carry the previous closeout forward")
        previous = session["after"]
    current = {w["id"]: [c["id"] for c in w["criteria"] if c["done"]] for w in workstreams}
    if current != previous:
        raise ValueError("progress current credit differs from latest session closeout")


def progress_markdown(state: dict) -> list[str]:
    rows = progress_rows(state)
    if not rows:
        return []
    tracking = state["workstream_progress"]
    output = ["## Workstream completion and session change", "",
        "Percentages measure verified checkpoints in the fixed **workstream-checklist-v1** rubric.",
        "They are a coarse capability assessment, not a fraction of remaining hours, a success probability,",
        "or an overall project percentage. Some checked capabilities are historical scoped proofs;",
        "the unchecked integration and fresh-run criteria require the current exact recipe.", "",
        "Baseline starts with this tracking history; no earlier session gains are invented.",
        "**pp** means percentage points: 40% to45% is +5pp. Regressions may reduce a score.", "",
        "| Workstream | Verified checkpoints | Completion | This session |",
        "| --- | ---: | ---: | ---: |"]
    for row in rows:
        output.append(f"| {row['title']} | {row['done']}/{row['total']} | {row['percent']:.1f}% | {row['delta']:+.1f}pp |")
    output += ["", "### Evidence checklist", "",
        "Equal checkpoint weights are a reporting convention; they do not imply equal difficulty.",
        "Adding or changing checkpoints requires a new rubric version and explicit rebaseline,",
        "reported separately from earned progress. Tracking/documentation alone earns no checkpoint.", ""]
    for w in tracking["workstreams"]:
        output += [f"#### {w['title']}", ""]
        groups = list(dict.fromkeys(c["group"] for c in w["criteria"] if c["group"]))
        for group in groups:
            items = [c for c in w["criteria"] if c["group"] == group]
            count = sum(c["done"] for c in items)
            output += [f"{group}: **{count}/{len(items)} ({100 * count / len(items):.1f}%)**.", ""]
        for c in w["criteria"]:
            link = f" ([evidence](../{c['evidence']['path']}))" if c["evidence"] else ""
            output.append(f"- [{'x' if c['done'] else ' '}] {c['label']}{link}")
        output.append("")
    output += ["### Recent session percentage-point history", "",
        "The latest ten sessions are shown here. The [complete existing history](../configs/development-roadmap-state.json) retains every before/after snapshot.", "",
        "| Session | " + " | ".join(w["id"] for w in tracking["workstreams"]) + " |",
        "| --- | " + " | ".join("---:" for _ in rows) + " |"]
    for session in tracking["sessions"][-10:]:
        cells = []
        for w in tracking["workstreams"]:
            total = len(w["criteria"]); key = w["id"]
            before = 100 * len(session["before"][key]) / total
            after = 100 * len(session["after"][key]) / total
            cells.append(f"{before:.1f}%→{after:.1f}% ({after-before:+.1f}pp)")
        output.append("| " + session["session"] + " | " + " | ".join(cells) + " |")
    output += ["", tracking["sessions"][-1]["note"], ""]
    return output


def _red_delivery_verified(state: dict) -> bool:
    gate = state.get("red_completion_gate", {})
    criteria = [value for key, value in gate.items() if key != "evidence"]
    return bool(criteria) and all(value is True for value in criteria)


def render_svg(baseline: dict, state: dict, lane: dict, evidence: dict) -> str:
    items = state["milestone"]["items"]
    done = sum(item["done"] for item in items)
    samples = evidence["fit"]["model"]["settled_examples"]
    dex_kind = "living" if baseline["baseline_id"] == "red-first-v1" else "registered"
    checklist_lines = [textwrap.wrap(item["label"], width=48) for item in items]
    checklist_height = sum(max(30, len(lines) * 20 + 10) for lines in checklist_lines)
    expansion = max(0, checklist_height + 40 - 299)
    review_lines = textwrap.wrap(state["reviews"][-1]["result"], width=125)
    review_footer_y = 1767 + expansion + len(review_lines) * 25 + 15
    progress_height = 600 if progress_rows(state) else 0
    review_footer_y += progress_height
    height = max(1870 + expansion + progress_height, review_footer_y + 40)
    colors = {
        "verified": "#57dfb1",
        "current": "#ffd36a",
        "planned": "#9daac4",
        "blocked": "#ff9387",
    }
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1420" height="{height}" '
        f'viewBox="0 0 1420 {height}" role="img" aria-labelledby="title description">',
        '<title id="title">Pokemon development roadmap</title>',
        f'<desc id="description">{done} of {len(items)} historical preparation items verified, '
        "not overall completion. Eight stages lead from the learning loop "
        f"to a cross-game {dex_kind} Pokedex.</desc>",
        "<style>text{font-family:Arial,Helvetica,sans-serif;fill:#edf3ff}.muted{fill:#adbad1}.eyebrow{font-size:16px;letter-spacing:2px;font-weight:bold}.heading{font-size:29px;font-weight:bold}.body{font-size:19px}.small{font-size:17px}</style>",
        f'<rect width="1420" height="{height}" fill="#0b1221"/>',
        '<path d="M1120 0H1420V225Z" fill="#172947"/>',
    ]

    def text(x, y, value, cls="body", color=None):
        fill = f' style="fill:{color}"' if color else ""
        parts.append(f'<text x="{x}" y="{y}" class="{cls}"{fill}>{html.escape(str(value))}</text>')

    def lines(x, y, value, width=63, cls="body", gap=25):
        for i, line in enumerate(textwrap.wrap(value, width=width)):
            text(x, y + i * gap, line, cls)

    text(50, 55, "POKEMON / DEVELOPMENT ATLAS", "eyebrow", "#57dfb1")
    parts.append(
        '<text x="50" y="125" style="font-size:49px;font-weight:bold">'
        f"From Red to a {dex_kind} Pokedex.</text>"
    )
    story_label = (
        "Fresh-start Red story"
        if baseline["baseline_id"]
        in {
            "red-first-v3-full-run",
            "red-first-v4-legitimate-native",
        }
        else "Checkpoint-based Red story"
    )
    text(
        50,
        168,
        "A fixed destination. Evidence-led steps. No hidden finish-line changes.",
        "body muted",
    )
    story_status = (
        "verified" if state["stages"]["red-story"]["status"] == "verified" else "not demonstrated"
    )
    text(
        50,
        215,
        f"Historical receipt: {samples} goal-value examples  /  {story_label}: {story_status}",
        "small",
    )
    parts.append(
        f'<rect x="50" y="260" width="1320" height="{395 + expansion}" rx="20" fill="#16243a"/>'
    )
    current_number = next(
        i + 1 for i, stage in enumerate(baseline["stages"]) if stage["id"] == state["current_stage"]
    )
    text(80, 304, f"YOU ARE HERE / PHASE {current_number:02d}", "eyebrow", "#ffd36a")
    text(80, 349, state["milestone"]["title"], "heading")
    parts.append(
        '<text x="80" y="456" style="font-size:56px;font-weight:bold;fill:#ffd36a">'
        + ('PROVEN' if _red_delivery_verified(state) else 'NOT PROVEN') + '</text>'
    )
    text(82, 495, f"{done} of {len(items)} historical preparation items", "body")
    text(82, 529, "Not completed campaigns or a time estimate.", "small muted")
    y = 326
    for item, wrapped in zip(items, checklist_lines, strict=True):
        color = "#57dfb1" if item["done"] else "#8594ad"
        text(705, y, "DONE" if item["done"] else "NEXT", "small", color)
        for offset, line in enumerate(wrapped):
            text(778, y + offset * 20, line, "small")
        y += max(30, len(wrapped) * 20 + 10)
    parts.append(
        f'<rect x="80" y="{625 + expansion}" width="1260" height="8" rx="4" fill="#293b55"/>'
    )
    if progress_height:
        text(50, 695 + expansion, "WORKSTREAM CHECKLIST COMPLETION", "eyebrow", "#57dfb1")
        text(50, 730 + expansion, "Fixed evidence checkpoints; not time remaining. Session changes in percentage points (pp).", "small muted")
        for index, row in enumerate(progress_rows(state)):
            y = 778 + expansion + index * 78
            text(80, y, row["title"], "body")
            text(910, y, f"{row['done']}/{row['total']}  {row['percent']:.1f}%  ({row['delta']:+.1f}pp)", "small", "#ffd36a")
            parts.append(f'<rect x="80" y="{y+15}" width="1260" height="12" rx="6" fill="#293b55"/>')
            parts.append(f'<rect x="80" y="{y+15}" width="{1260*row["percent"]/100:g}" height="12" rx="6" fill="#57dfb1"/>')
        text(80, 1240 + expansion, "Baseline established now. Historical scoped proof is distinct from current-recipe integration.", "small muted")
    text(50, 695 + expansion + progress_height, "THE WHOLE JOURNEY", "eyebrow")
    text(740, 695 + expansion + progress_height, "VERIFIED", "small", colors["verified"])
    text(870, 695 + expansion + progress_height, "CURRENT", "small", colors["current"])
    text(1000, 695 + expansion + progress_height, "PLANNED / NOT DEMONSTRATED", "small", colors["planned"])
    for i, stage in enumerate(baseline["stages"]):
        x, y = 50 + (i % 2) * 680, 735 + expansion + progress_height + (i // 2) * 225
        status = state["stages"][stage["id"]]["status"]
        color = colors[status]
        fill = "#202d3d" if status == "current" else "#111e31"
        parts.append(f'<rect x="{x}" y="{y}" width="640" height="205" rx="14" fill="{fill}"/>')
        parts.append(f'<rect x="{x}" y="{y + 22}" width="4" height="161" rx="2" fill="{color}"/>')
        text(x + 24, y + 31, f"{i + 1:02d} / {status.upper()}", "eyebrow", color)
        text(x + 24, y + 72, stage["title"], "heading")
        lines(x + 24, y + 106, stage["goal"], width=57, gap=24)
        lines(x + 24, y + 155, stage["scope"], width=68, cls="small muted", gap=19)
    text(50, 1694 + expansion + progress_height, "SESSION CHECK-IN", "eyebrow", "#57dfb1")
    text(50, 1732 + expansion + progress_height, state["as_of_session"], "small muted")
    lines(50, 1767 + expansion + progress_height, state["reviews"][-1]["result"], width=125)
    text(
        50,
        review_footer_y,
        f"Baseline {baseline['baseline_id']} / "
        "Exit criteria and evidence: docs/development-roadmap.md",
        "small muted",
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_markdown(baseline: dict, state: dict, lane: dict, evidence: dict) -> str:
    items = state["milestone"]["items"]
    done = sum(item["done"] for item in items)
    result = [
        "<!-- Generated by scripts/development_roadmap.py; "
        "edit the baseline/state, not this file. -->",
        "# Development roadmap",
        "",
        "![Development infographic](assets/development-roadmap.svg)",
        "",
        f"Baseline: **{baseline['baseline_id']}**. Reviewed through **{state['as_of_session']}**.",
        "",
        baseline["mission"],
        "",
        "## Delivery status",
        "",
        f"**{state['milestone']['title']}: "
        + ("proved." if _red_delivery_verified(state) else "not yet proved.") + "**",
        "Use the [six workstreams and milestone ladder](model-first-roadmap.md) for the active delivery plan.",
        "",
        "<details>",
        f"<summary>Historical preparation receipts: {done} of {len(items)} items</summary>",
        "",
        "These earlier component/reference receipts are not a full-run success rate or a project percentage.",
        "",
    ]
    for item in items:
        link = f" ([evidence](../{item['evidence']}))" if item["evidence"] else ""
        result.append(f"- [{'x' if item['done'] else ' '}] {item['label']}{link}")
    result += [
        "",
        "</details>",
        "",
        f"Pinned historical learning receipt: **{evidence['fit']['model']['settled_examples']} "
        "examples**. The current model and integration boundary are reported below in the "
        "latest review and active state; this older chart receipt is not full-game competence.",
        "",
    ]
    result += progress_markdown(state)
    result += ["## Stable goals and exit criteria", ""]
    result += ["| Stage and status | Goal | Exit criterion | Scope and evidence |", "| --- | --- | --- | --- |"]
    cell = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
    for i, stage in enumerate(baseline["stages"]):
        row = state["stages"][stage["id"]]
        link = f" [Evidence](../{row['evidence']})" if row["evidence"] else ""
        result.append(f"| {i + 1:02d}. {cell(stage['title'])} — {row['status']} | {cell(stage['goal'])} | {cell(stage['exit'])} | {cell(stage['scope'])}{link} |")
    result.append("")
    result += [
        "## Latest review",
        "",
        "Earlier reviews remain in the [status history](../configs/development-roadmap-state.json)",
        "and dated work-session reports. Their next steps are not current instructions.",
        "",
    ]
    for review in state["reviews"][-1:]:
        result += [
            f"### {review['session']}",
            "",
            review["result"],
            "",
            f"**Deviation:** {review['deviation']}",
            "",
            f"**Next:** {review['next']}",
            "",
        ]
    result += [
        "## Update contract",
        "",
        "After every session, append the before/after checkpoint snapshot and explain each gain or regression. "
        "After a material learner milestone, strategy/requirements change "
        "or explicit request, update "
        "the [status record](../configs/development-roadmap-state.json), "
        "preserve the review history, "
        "and regenerate this page and graphic. Record changes to the stable goals in "
        "[roadmap decisions](roadmap-decisions.md).",
        "",
        "The [North Star](../NORTH_STAR.md) and "
        "[active product state](../ACTIVE_PRODUCT_STATE.md) remain authoritative. "
        "The existing documentation check detects stale generated output; "
        "no new CI workflow is required.",
        "",
    ]
    return "\n".join(result)


def check_roadmap(root: Path = ROOT, *, write: bool = False) -> None:
    args = load_roadmap(root)
    for relative, payload in ((SVG, render_svg(*args)), (MARKDOWN, render_markdown(*args))):
        path = root / relative
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload)
        elif not path.exists() or path.read_text() != payload:
            raise ValueError("development roadmap is stale; update status and regenerate")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    check_roadmap(write=parser.parse_args().write)
    print("Development roadmap is current.")
