"""Keep public entry points readable without suppressing historical evidence."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CURRENT_PAGES = (
    "HANDOFF.md",
    "AGENT_COORDINATION.md",
    "docs/current-agent-handoffs.md",
    "docs/model-first-roadmap.md",
    "docs/architecture.md",
    "docs/portfolio-brief.md",
    "docs/project-narrative.md",
    "docs/youtube-video-narrative.md",
    "docs/progress-dashboard.md",
)


def test_readme_is_a_short_public_introduction() -> None:
    text = (ROOT / "README.md").read_text()
    assert len(text.splitlines()) <= 100
    assert len(text.split()) <= 650
    assert text.startswith("# Pokémon Red Completion Agent\n")
    assert "## What works today" in text
    assert "## What is not solved" in text
    assert "## Authorship" in text
    assert "AI-assisted" in text
    assert "docs/worklog.md" in text
    assert "Current product focus" not in text
    assert "Prior checkpoints" not in text


@pytest.mark.parametrize("relative", ("README.md", *CURRENT_PAGES))
def test_current_pages_do_not_accumulate_status_logs(relative: str) -> None:
    lines = (ROOT / relative).read_text().splitlines()
    assert len(lines) <= 200
    assert sum(line.startswith("# ") for line in lines) == 1
    assert not any("Prior checkpoints" in line for line in lines)


def test_historical_entry_points_are_explicitly_superseded() -> None:
    archives = (ROOT / "docs/history").glob("*-through-2026-09-10.md")
    paths = [ROOT / "docs/worklog.md", *archives]
    assert len(paths) == 10
    for path in paths:
        first = path.read_text().splitlines()[0]
        assert first == "# Historical archive — superseded September 10, 2026"
