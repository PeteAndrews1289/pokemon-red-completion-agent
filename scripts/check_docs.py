#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

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

    if problems:
        print("\n".join(problems))
        return 1
    print("Documentation links passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
