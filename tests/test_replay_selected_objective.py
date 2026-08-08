from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from replay_selected_objective import _training_candidate_control_report  # noqa: E402


class _CandidateAudit:
    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-training-candidate-runtime-audit-v1",
            "decisions": 17,
            "model_had_execution_authority": False,
            "authority_choice_kinds": [],
            "teacher_fallback_on_model_disagreement": None,
        }


def test_portable_candidate_report_separates_shadow_from_live_authority() -> None:
    shadow = _training_candidate_control_report(
        _CandidateAudit(),  # type: ignore[arg-type]
        model_file_sha256="a" * 64,
        authority=False,
        controlled_decisions=0,
    )
    controlled = _training_candidate_control_report(
        _CandidateAudit(),  # type: ignore[arg-type]
        model_file_sha256="a" * 64,
        authority=True,
        controlled_decisions=17,
    )

    assert shadow is not None
    assert shadow["authority_choice_kinds"] == []
    assert shadow["model_had_execution_authority"] is False
    assert shadow["teacher_fallback_on_model_disagreement"] is None
    assert controlled is not None
    assert controlled["authority_choice_kinds"] == ["trainee", "venue"]
    assert controlled["model_had_execution_authority"] is True
    assert controlled["teacher_fallback_on_model_disagreement"] is False
    assert controlled["portable_runtime_recertified"] is False
    assert controlled["promotion_eligible"] is False


def test_portable_candidate_report_is_absent_without_a_model() -> None:
    assert (
        _training_candidate_control_report(
            None,
            model_file_sha256=None,
            authority=False,
            controlled_decisions=0,
        )
        is None
    )
