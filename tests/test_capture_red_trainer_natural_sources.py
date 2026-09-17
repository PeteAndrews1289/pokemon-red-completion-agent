"""ROM-free admission checks for the prospective natural trainer captures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pokemon_red_completion.red_trainer_practice_ancestry import trainer_origin_cluster

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import capture_red_cinnabar_burglar_development_source as cinnabar  # noqa: E402
import capture_red_league_development_sources as league  # noqa: E402
import capture_red_lorelei_development_source as lorelei  # noqa: E402


def test_league_source_bindings_match_predeclared_cohort() -> None:
    declaration = json.loads(
        (ROOT / "configs/red-trainer-league-development-cohort-2026-09-17.json").read_text()
    )
    assert declaration["status_at_declaration"] == "no_cohort_battles_played"
    assert declaration["ancestry"] == "all_three_share_one_unresolved_historical_red_progression"
    assert trainer_origin_cluster(league.LINEAGE_ID) == "unresolved-legacy-red-origin"
    assert len(declaration["cohort"]) == 3
    for item in declaration["cohort"]:
        source = league.SOURCES[item["encounter"]]
        assert source["file"] == item["source"]
        assert source["sha256"] == item["source_sha256"]
        assert declaration["rom_sha256"] == league.ROM_SHA256


@pytest.mark.parametrize("stage", ("bruno", "agatha", "lance"))
def test_league_collector_rejects_wrong_source_before_gameplay(tmp_path: Path, stage: str) -> None:
    with pytest.raises(ValueError, match="source identity differs"):
        league.run(stage, tmp_path / "missing.gb", tmp_path / "wrong.state", tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("collector", (cinnabar, lorelei))
def test_single_trainer_collectors_reject_wrong_source_before_gameplay(
    tmp_path: Path, collector: object
) -> None:
    with pytest.raises(ValueError, match="source identity differs"):
        collector.run(tmp_path / "missing.gb", tmp_path / "wrong.state", tmp_path / "out")
    assert not (tmp_path / "out").exists()
