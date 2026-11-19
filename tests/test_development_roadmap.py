import json
import shutil
from xml.etree import ElementTree

import pytest
from development_roadmap import ROOT, STATE, SVG, check_roadmap, load_roadmap, render_svg


@pytest.fixture
def project(tmp_path):
    names = [
        STATE,
        "configs/development-roadmap-baseline-v1.json",
        "configs/active-product-focus.json",
        "configs/dashboard-learning-evidence.json",
    ]
    names.append("configs/development-roadmap-baseline-v2.json")
    names.append("configs/development-roadmap-baseline-v3.json")
    names.append("configs/development-roadmap-baseline-v4.json")
    state = json.loads((ROOT / STATE).read_text())
    names += [row["evidence"] for row in state["stages"].values() if row["evidence"]]
    names += [row["evidence"] for row in state["milestone"]["items"] if row["evidence"]]
    names += [json.loads((ROOT / names[3]).read_text())["path"]]
    names += [c["evidence"]["path"] for w in state["workstream_progress"]["workstreams"]
              for c in w["criteria"] if c["evidence"]]
    for name in set(names):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def test_current_graphic_and_accessible_page_are_reproducible(project):
    baseline, state, lane, evidence = load_roadmap(project)
    # A controlled rendering fixture, independent of the advancing live status.
    state["milestone"]["items"] = [
        {"label": f"Fixture criterion {i}", "done": i < 2} for i in range(5)
    ]
    evidence["fit"]["model"]["settled_examples"] = 32
    state["current_stage"] = "adaptive-red"
    state["stages"]["red-story"]["status"] = "planned"
    svg = render_svg(baseline, state, lane, evidence)
    check_roadmap(project, write=True)
    check_roadmap(project)
    ElementTree.fromstring(svg)
    assert "2 of 5 historical preparation items" in svg and "32 goal-value examples" in svg
    assert "40%" not in svg and "NOT PROVEN" in svg
    assert "PHASE 02" in svg and "not demonstrated" in svg
    assert "Not completed campaigns or a time estimate." in svg
    assert "Transfer and learn Crystal" in svg
    assert "cross-game registered Dex" in svg
    (project / SVG).write_text((project / SVG).read_text() + "<!-- stale -->")
    with pytest.raises(ValueError, match="stale"):
        check_roadmap(project)


@pytest.mark.parametrize("change", ["stale_session", "two_current", "missing_evidence"])
def test_status_drift_is_caught_before_publication(project, change):
    state = json.loads((project / STATE).read_text())
    if change == "stale_session":
        state["as_of_session"] = "old-session"
    elif change == "two_current":
        other = next(key for key in state["stages"] if key != state["current_stage"])
        state["stages"][other]["status"] = "current"
    else:
        # Exercise a false completion claim even when the live roadmap's first
        # item is still planned. Removing an already-null field is not a probe.
        state["milestone"]["items"][0]["done"] = True
        state["milestone"]["items"][0]["evidence"] = None
    (project / STATE).write_text(json.dumps(state))
    with pytest.raises(ValueError):
        load_roadmap(project)


def test_planned_checklist_item_does_not_require_completed_evidence(project):
    state = json.loads((project / STATE).read_text())
    state["milestone"]["items"][0]["done"] = False
    state["milestone"]["items"][0]["evidence"] = None
    (project / STATE).write_text(json.dumps(state))
    _, loaded, _, _ = load_roadmap(project)
    assert loaded["milestone"]["items"][0]["done"] is False


def test_graphic_updates_current_position_and_checklist_without_static_claims(project):
    baseline, state, lane, evidence = load_roadmap(project)
    state["stages"]["adaptive-red"]["status"] = "verified"
    state["stages"]["red-story"]["status"] = "current"
    state["current_stage"] = "red-story"
    state["milestone"]["items"] = [
        {"label": f"Fixture criterion {i}", "done": i < 3} for i in range(5)
    ]
    evidence["fit"]["model"]["settled_examples"] = 47
    graphic = render_svg(baseline, state, lane, evidence)
    assert "3 of 5 historical preparation items" in graphic and "PHASE 04" in graphic
    assert "60%" not in graphic and "NOT PROVEN" in graphic
    assert "47 goal-value examples" in graphic
    assert "Fresh-start Red story: not demonstrated" in graphic
    state["stages"]["red-story"]["status"] = "verified"
    assert "Fresh-start Red story: verified" in render_svg(baseline, state, lane, evidence)


def test_ten_item_checklist_stays_above_its_progress_bar(project):
    baseline, state, lane, evidence = load_roadmap(project)
    state["milestone"]["items"] = [
        {"label": f"Fixture criterion {i}", "done": i < 9} for i in range(10)
    ]

    root = ElementTree.fromstring(render_svg(baseline, state, lane, evidence))
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    checklist = [
        node
        for node in root.findall("svg:text", namespace)
        if node.get("x") == "778" and (node.text or "").startswith("Fixture criterion")
    ]
    progress = next(
        node
        for node in root.findall("svg:rect", namespace)
        if node.get("x") == "80" and node.get("width") == "1260"
    )

    assert len(checklist) == 10
    assert max(int(node.get("y", "0")) for node in checklist) + 20 < int(progress.get("y", "0"))


def test_long_session_result_does_not_overlap_footer_or_clip_svg(project):
    baseline, state, lane, evidence = load_roadmap(project)
    state["reviews"][-1]["result"] = "A long measured review. " * 100
    root = ElementTree.fromstring(render_svg(baseline, state, lane, evidence))
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    texts = root.findall("svg:text", namespace)
    review_heading = next(
        node for node in texts if (node.text or "") == "SESSION CHECK-IN"
    )
    footer = next(
        node for node in texts if (node.text or "").startswith("Baseline red-first-")
    )
    body_rows = [
        node for node in texts
        if node.get("x") == "50"
        and node.get("class") == "body"
        and int(node.get("y", "0")) > int(review_heading.get("y", "0"))
    ]
    assert body_rows
    assert int(footer.get("y", "0")) - max(int(row.get("y", "0")) for row in body_rows) >= 20
    assert int(root.get("height", "0")) > int(footer.get("y", "0"))


def test_changed_learning_evidence_is_rejected(project):
    ref = json.loads((project / "configs/dashboard-learning-evidence.json").read_text())
    path = project / ref["path"]
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="evidence changed"):
        load_roadmap(project)


def test_registered_baseline_is_explicit_and_old_baseline_remains_available(project):
    baseline, state, lane, evidence = load_roadmap(project)
    assert baseline["baseline_id"] == "red-first-v4-legitimate-native"
    assert "From Red to a registered Pokedex" in render_svg(baseline, state, lane, evidence)
    state["baseline_id"] = "red-first-v1"
    (project / STATE).write_text(json.dumps(state))
    old, loaded, _, _ = load_roadmap(project)
    assert "From Red to a living Pokedex" in render_svg(old, loaded, lane, evidence)
    assert old["stages"][4]["exit"] != baseline["stages"][4]["exit"]
    assert [s["id"] for s in old["stages"]] == [s["id"] for s in baseline["stages"]]
    state["baseline_id"] = "red-first-v3-full-run"
    state["red_completion_gate"] = {
        "fresh_start": False,
        "model_directed_start_to_finish": False,
        "champion_and_hall_of_fame": False,
        "full_local_red_pokedex": False,
        "legitimate_external_dependencies_resolved": False,
        "evidence": None,
    }
    (project / STATE).write_text(json.dumps(state))
    previous, _, _, _ = load_roadmap(project)
    assert previous["baseline_id"] == "red-first-v3-full-run"
    state["baseline_id"] = "unapproved-baseline"
    (project / STATE).write_text(json.dumps(state))
    with pytest.raises(ValueError, match="explicit adoption"):
        load_roadmap(project)


@pytest.mark.parametrize("stage", ["red-hack", "crystal", "cross-generation"])
def test_cannot_advance_beyond_red_with_incomplete_full_run_gate(project, stage):
    state = json.loads((project / STATE).read_text())
    state["stages"][state["current_stage"]]["status"] = "planned"
    state["stages"][stage] = {
        "status": "current",
        # Use existing evidence so this probes the final-run gate even when
        # the current implementation checklist is entirely unfinished.
        "evidence": state["stages"]["red-story"]["evidence"],
    }
    state["current_stage"] = stage
    (project / STATE).write_text(json.dumps(state))
    with pytest.raises(ValueError, match="before any ROM hack"):
        load_roadmap(project)


def test_full_red_claims_require_explicit_evidence(project):
    state = json.loads((project / STATE).read_text())
    state["red_completion_gate"]["fresh_start"] = True
    (project / STATE).write_text(json.dumps(state))
    with pytest.raises(ValueError, match="require evidence"):
        load_roadmap(project)


def test_long_realistic_checklist_expands_without_clipping(project):
    baseline, state, lane, evidence = load_roadmap(project)
    state["milestone"]["items"] = [
        {
            "label": f"Criterion {i}: retain the exact measured outcome and all its source bindings",  # noqa: E501
            "done": False,
        }
        for i in range(17)
    ]
    root = ElementTree.fromstring(render_svg(baseline, state, lane, evidence))
    ns = {"svg": "http://www.w3.org/2000/svg"}
    labels = [node for node in root.findall("svg:text", ns) if node.get("x") == "778"]
    progress = next(
        node
        for node in root.findall("svg:rect", ns)
        if node.get("x") == "80" and node.get("width") == "1260"
    )
    assert len(labels) > 17
    assert max(int(node.get("y")) for node in labels) + 20 < int(progress.get("y"))
    assert all(len(node.text or "") <= 48 for node in labels)

def test_progress_credit_needs_exact_unchanged_evidence(project):
    state = json.loads((project / STATE).read_text())
    item = state["workstream_progress"]["workstreams"][0]["criteria"][0]
    (project / item["evidence"]["path"]).write_text('{}')
    with pytest.raises(ValueError, match="progress evidence changed"):
        load_roadmap(project)


def test_adding_easy_checkpoint_cannot_inflate_denominator(project):
    state = json.loads((project / STATE).read_text())
    work = state["workstream_progress"]["workstreams"][0]
    work["criteria"].append(dict(work["criteria"][0], id="extra-easy-check"))
    (project / STATE).write_text(json.dumps(state))
    with pytest.raises(ValueError, match="denominator changed"):
        load_roadmap(project)


def test_progress_baseline_does_not_invent_prior_gains(project):
    from development_roadmap import progress_rows
    _, state, _, _ = load_roadmap(project)
    baseline_state = {**state, "workstream_progress": {**state["workstream_progress"],
        "sessions": state["workstream_progress"]["sessions"][:1]}}
    assert all(row["delta"] == 0 for row in progress_rows(baseline_state))
    first = state["workstream_progress"]["sessions"][0]
    first["before"]["execution"] = []
    (project / STATE).write_text(json.dumps(state))
    with pytest.raises(ValueError, match="baseline cannot invent"):
        load_roadmap(project)


def test_regression_is_negative_and_history_carries_forward(project):
    from copy import deepcopy
    from development_roadmap import progress_rows, validate_progress
    _, state, _, _ = load_roadmap(project)
    track = state["workstream_progress"]
    before = deepcopy(track["sessions"][-1]["after"])
    after = deepcopy(before)
    lost = after["execution"].pop(0)
    track["workstreams"][0]["criteria"][0]["done"] = False
    state["as_of_session"] = "regression-session"
    track["sessions"].append(dict(session="regression-session",kind="session",before=before,after=after,note="Regression retained"))
    validate_progress(project, state)
    row = progress_rows(state)[0]
    assert row["delta"] == -12.5 and row["percent"] == row["before"] - 12.5
    track["sessions"][-1]["before"]["execution"].remove(lost)
    with pytest.raises(ValueError, match="previous closeout"):
        validate_progress(project, state)


def test_workstream_credit_cannot_pass_fresh_run_delivery(project):
    from development_roadmap import render_markdown
    baseline, state, lane, evidence = load_roadmap(project)
    page = render_markdown(baseline, state, lane, evidence)
    assert "62.5%" in page and "+0.0pp" in page
    assert "not yet proved" in page and "0/6" in page
    svg = ElementTree.fromstring(render_svg(baseline, state, lane, evidence))
    ns = {"s":"http://www.w3.org/2000/svg"}
    texts = svg.findall("s:text", ns)
    last_progress = next(t for t in texts if (t.text or "").startswith("Baseline established now"))
    next_heading = next(t for t in texts if t.text == "THE WHOLE JOURNEY")
    assert int(next_heading.get("y")) - int(last_progress.get("y")) >= 40
