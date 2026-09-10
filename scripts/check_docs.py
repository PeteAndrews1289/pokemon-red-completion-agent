#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from check_product_focus import check_product_focus
from development_roadmap import check_roadmap
from product_focus import ProductFocusError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
IGNORED_PREFIXES = ("#", "http://", "https://", "mailto:")
IGNORED_DIRECTORIES = {".git", ".venv", "scratch"}


def main() -> int:
    problems: list[str] = []
    for document in sorted(PROJECT_ROOT.rglob("*.md")):
        if any(
            part in IGNORED_DIRECTORIES
            for part in document.relative_to(PROJECT_ROOT).parts
        ):
            continue
        text = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(IGNORED_PREFIXES):
                continue
            relative_target = unquote(target.split("#", 1)[0])
            resolved = (document.parent / relative_target).resolve()
            if not resolved.exists():
                problems.append(
                    f"{document.relative_to(PROJECT_ROOT)}: missing link target {target!r}"
                )

    try:
        check_product_focus()
    except ProductFocusError as error:
        problems.append(f"active product focus: {error}")

    try:
        check_roadmap()
    except (ValueError, KeyError, OSError) as error:
        problems.append(f"development roadmap: {error}")

    if problems:
        print("\n".join(problems))
        return 1
    print("Documentation links and active product focus passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
