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
    if baseline_id != "red-first-v1":
        raise ValueError("new roadmap baseline requires explicit adoption in the renderer")
    baseline = _read(root, "configs/development-roadmap-baseline-v1.json")
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
    return baseline, state, lane, evidence


def render_svg(baseline: dict, state: dict, lane: dict, evidence: dict) -> str:
    items = state["milestone"]["items"]
    done = sum(item["done"] for item in items)
    percentage = round(100 * done / len(items))
    samples = evidence["fit"]["model"]["settled_examples"]
    colors = {
        "verified": "#57dfb1",
        "current": "#ffd36a",
        "planned": "#9daac4",
        "blocked": "#ff9387",
    }
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1420" height="1870" '
        'viewBox="0 0 1420 1870" role="img" aria-labelledby="title description">',
        '<title id="title">Pokemon development roadmap</title>',
        f'<desc id="description">{done} of {len(items)} current checklist items verified, '
        "not overall completion. Eight stages lead from the learning loop "
        "to a cross-game living Pokedex.</desc>",
        "<style>text{font-family:Arial,Helvetica,sans-serif;fill:#edf3ff}.muted{fill:#adbad1}.eyebrow{font-size:16px;letter-spacing:2px;font-weight:bold}.heading{font-size:29px;font-weight:bold}.body{font-size:19px}.small{font-size:17px}</style>",
        '<rect width="1420" height="1870" fill="#0b1221"/>',
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
        "From Red to a living Pokedex.</text>"
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
        f"{samples} goal-value examples  /  Full model-led Red win: {story_status}",
        "small",
    )
    parts.append('<rect x="50" y="260" width="1320" height="365" rx="20" fill="#16243a"/>')
    current_number = next(
        i + 1 for i, stage in enumerate(baseline["stages"]) if stage["id"] == state["current_stage"]
    )
    text(80, 304, f"YOU ARE HERE / PHASE {current_number:02d}", "eyebrow", "#ffd36a")
    text(80, 349, state["milestone"]["title"], "heading")
    parts.append(
        '<text x="80" y="456" style="font-size:88px;font-weight:bold;fill:#ffd36a">'
        f"{percentage}%</text>"
    )
    text(82, 495, f"{done} of {len(items)} acceptance items verified", "body")
    text(82, 529, "Not Red completion. Not a time estimate.", "small muted")
    for i, item in enumerate(items):
        y = 342 + i * 44
        color = "#57dfb1" if item["done"] else "#8594ad"
        text(705, y, "DONE" if item["done"] else "NEXT", "small", color)
        text(778, y, item["label"], "body")
    parts.append('<rect x="80" y="577" width="1260" height="8" rx="4" fill="#293b55"/>')
    parts.append(
        f'<rect x="80" y="577" width="{1260 * done / len(items):g}" '
        'height="8" rx="4" fill="#ffd36a"/>'
    )
    text(50, 695, "THE WHOLE JOURNEY", "eyebrow")
    text(740, 695, "VERIFIED", "small", colors["verified"])
    text(870, 695, "CURRENT", "small", colors["current"])
    text(1000, 695, "PLANNED / NOT DEMONSTRATED", "small", colors["planned"])
    for i, stage in enumerate(baseline["stages"]):
        x, y = 50 + (i % 2) * 680, 735 + (i // 2) * 225
        status = state["stages"][stage["id"]]["status"]
        color = colors[status]
        fill = "#202d3d" if status == "current" else "#111e31"
        parts.append(f'<rect x="{x}" y="{y}" width="640" height="205" rx="14" fill="{fill}"/>')
        parts.append(f'<rect x="{x}" y="{y + 22}" width="4" height="161" rx="2" fill="{color}"/>')
        text(x + 24, y + 31, f"{i + 1:02d} / {status.upper()}", "eyebrow", color)
        text(x + 24, y + 72, stage["title"], "heading")
        lines(x + 24, y + 106, stage["goal"], width=57, gap=24)
        lines(x + 24, y + 163, stage["scope"], width=68, cls="small muted", gap=21)
    text(50, 1694, "SESSION CHECK-IN", "eyebrow", "#57dfb1")
    text(50, 1732, state["as_of_session"], "small muted")
    lines(50, 1767, state["reviews"][-1]["result"], width=125)
    text(
        50,
        1830,
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
        "## Current milestone",
        "",
        f"**{state['milestone']['title']}: {done}/{len(items)} acceptance items "
        f"({round(100 * done / len(items))}%).**",
        "This is a checklist, not project completion or a remaining-time estimate.",
        "",
    ]
    for item in items:
        link = f" ([evidence](../{item['evidence']}))" if item["evidence"] else ""
        result.append(f"- [{'x' if item['done'] else ' '}] {item['label']}{link}")
    result += [
        "",
        f"Current model: **{evidence['fit']['model']['settled_examples']} examples**. "
        "This is a small goal-value learner, not a demonstrated full-game player.",
        "",
        "## Stable goals and exit criteria",
        "",
    ]
    for i, stage in enumerate(baseline["stages"]):
        row = state["stages"][stage["id"]]
        result += [
            f"### {i + 1:02d}. {stage['title']} — {row['status']}",
            "",
            stage["goal"],
            "",
            f"**Exit criterion:** {stage['exit']}",
            "",
            stage["scope"],
            "",
        ]
        if row["evidence"]:
            result += [f"[Current evidence](../{row['evidence']})", ""]
    result += ["## Session reviews", ""]
    for review in reversed(state["reviews"]):
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
        "After each completed session or substantial verified milestone, update "
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
