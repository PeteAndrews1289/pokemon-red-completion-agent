from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from run_portable_clean_start import main  # noqa: E402


def test_portable_clean_start_cli_imports_and_exposes_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    captured = capsys.readouterr()
    assert raised.value.code == 0
    assert "uncounted portable clean-start" in captured.out
    assert "--diagnostic-seed" in captured.out
    assert "--objective-model" in captured.out
