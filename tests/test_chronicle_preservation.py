"""Keep the long-form history discoverable without expanding current status pages."""

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = (
    (
        "project-narrative-through-2026-09-10.md",
        "deb00db88115af0edca231c5c1aded958b52e3141472cc33b72e0649036e6b1e",
    ),
    (
        "video-narrative-through-2026-09-10.md",
        "5d24c947fffc936d97fa51d315c6760b3f20a0e17379bcbdf66ebbd198174e43",
    ),
)
CHAPTERS = (
    "01-teacher-and-first-learners.md",
    "02-evaluation-and-refocus.md",
    "03-scenarios-and-strategic-learning.md",
    "04-continuous-collection.md",
    "05-economy-and-runtime.md",
    "06-battle-classroom.md",
    "07-player-and-story.md",
    "08-preparation-and-routing.md",
)


@pytest.mark.parametrize(("name", "digest"), ARCHIVES)
def test_original_narrative_archives_remain_byte_identical(name: str, digest: str) -> None:
    assert hashlib.sha256((ROOT / "docs/history" / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("name", CHAPTERS)
def test_dated_chapters_are_retained_and_linked(name: str) -> None:
    index = (ROOT / "docs/chronicle/README.md").read_text()
    assert f"]({name})" in index
    chapter = (ROOT / "docs/chronicle" / name).read_text()
    assert sum(line.startswith("# ") for line in chapter.splitlines()) == 1
    assert "](README.md)" in chapter
    assert re.search(r"\]\(\.\./(?:evidence|work-sessions|history)/", chapter)


def test_raw_section_directory_keeps_all_archive_headings() -> None:
    directory = (ROOT / "docs/chronicle/ARCHIVE_SECTIONS.md").read_text()
    count = 0
    for name, digest in ARCHIVES:
        assert digest in directory
        lines = (ROOT / "docs/history" / name).read_text().splitlines()
        for number, line in enumerate(lines, 1):
            if re.match(r"^#{1,3} ", line):
                title = re.sub(r"^#+ +", "", line)
                title = title.replace("[", r"\[").replace("]", r"\]")
                assert f"- Line {number}: {title}\n" in directory
                count += 1
    assert count == 904


def test_chronicle_is_discoverable_from_reader_entry_points() -> None:
    for name in ("README.md", "docs/README.md", "docs/project-narrative.md"):
        assert "chronicle/README.md" in (ROOT / name).read_text()
    video = (ROOT / "docs/youtube-video-narrative.md").read_text()
    assert "chronicle/video-script-through-2026-09-22.md" in video
    assert "history/video-narrative-before-chronicle-2026-09-22.md" in video
    assert "preserve" in (ROOT / "docs/chronicle/README.md").read_text().lower()
