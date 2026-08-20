#!/usr/bin/env python3
"""Fail closed when the compact active product state is stale or weakened."""

from __future__ import annotations

import argparse
from pathlib import Path

from product_focus import (
    DEFAULT_FOCUS_CONFIG,
    DEFAULT_FOCUS_DOCUMENT,
    PROJECT_ROOT,
    ProductFocusError,
    focus_scorecard,
    load_product_focus,
    render_product_focus_markdown,
)

_REQUIRED_DISCOVERY_LINKS = {
    "AGENTS.md": "ACTIVE_PRODUCT_STATE.md",
    "AGENT_COORDINATION.md": "ACTIVE_PRODUCT_STATE.md",
    "HANDOFF.md": "ACTIVE_PRODUCT_STATE.md",
    "MISSION.md": "ACTIVE_PRODUCT_STATE.md",
    "NORTH_STAR.md": "ACTIVE_PRODUCT_STATE.md",
    "README.md": "ACTIVE_PRODUCT_STATE.md",
    "docs/model-first-roadmap.md": "../ACTIVE_PRODUCT_STATE.md",
    "docs/progress-dashboard.md": "../ACTIVE_PRODUCT_STATE.md",
    "docs/three-agent-workflow.md": "../ACTIVE_PRODUCT_STATE.md",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_FOCUS_CONFIG)
    parser.add_argument("--document", type=Path, default=DEFAULT_FOCUS_DOCUMENT)
    parser.add_argument("--print-status", action="store_true")
    return parser


def check_product_focus(
    *,
    config_path: Path = DEFAULT_FOCUS_CONFIG,
    document_path: Path = DEFAULT_FOCUS_DOCUMENT,
    project_root: Path = PROJECT_ROOT,
) -> tuple[str, ...]:
    state = load_product_focus(config_path, project_root=project_root)
    expected = render_product_focus_markdown(state)
    try:
        actual = document_path.read_text(encoding="utf-8")
    except OSError:
        raise ProductFocusError("generated active product state is unavailable") from None
    if actual != expected:
        raise ProductFocusError(
            "ACTIVE_PRODUCT_STATE.md differs from configs/active-product-focus.json"
        )
    for relative, target in _REQUIRED_DISCOVERY_LINKS.items():
        path = project_root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            raise ProductFocusError(
                f"focus discovery document is unavailable: {relative}"
            ) from None
        if target not in text:
            raise ProductFocusError(f"focus discovery link is missing from {relative}")
    template = (project_root / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )
    for field in (
        "Reusable capability",
        "Learned authority",
        "Transfer test",
        "Cheapest falsifier",
        "Time box",
        "Stop condition",
    ):
        if field not in template:
            raise ProductFocusError(f"pull request mission check is missing {field}")
    return tuple(
        f"{label}: {current}/{minimum}"
        for label, current, minimum in focus_scorecard(state)
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    rows = check_product_focus(config_path=args.config, document_path=args.document)
    if args.print_status:
        print("\n".join(rows))
    else:
        print("Active product focus passed: " + " · ".join(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
