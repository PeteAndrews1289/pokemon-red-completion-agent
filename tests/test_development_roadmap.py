import json
import shutil
from xml.etree import ElementTree

import pytest
from development_roadmap import ROOT, STATE, SVG, check_roadmap, load_roadmap, render_svg


@pytest.fixture
def project(tmp_path):
    names = [STATE, "configs/development-roadmap-baseline-v1.json",
             "configs/active-product-focus.json", "configs/dashboard-learning-evidence.json"]
    state = json.loads((ROOT / STATE).read_text())
    names += [row["evidence"] for row in state["stages"].values() if row["evidence"]]
    names += [row["evidence"] for row in state["milestone"]["items"] if row["evidence"]]
    names += [json.loads((ROOT / names[3]).read_text())["path"]]
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
    assert "40%" in svg and "32 goal-value examples" in svg
    assert "PHASE 02" in svg and "not demonstrated" in svg
    assert "Not Red completion. Not a time estimate." in svg
    assert "Transfer and learn Crystal" in svg
    assert "cross-game living Dex" in svg
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
        state["milestone"]["items"][0]["evidence"] = None
    (project / STATE).write_text(json.dumps(state))
    with pytest.raises(ValueError):
        load_roadmap(project)


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
    assert "60%" in graphic and "PHASE 04" in graphic
    assert "47 goal-value examples" in graphic
    assert "Full model-led Red win: not demonstrated" in graphic
    state["stages"]["red-story"]["status"] = "verified"
    assert "Full model-led Red win: verified" in render_svg(baseline, state, lane, evidence)


def test_changed_learning_evidence_is_rejected(project):
    ref = json.loads((project / "configs/dashboard-learning-evidence.json").read_text())
    path = project / ref["path"]
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="evidence changed"):
        load_roadmap(project)
