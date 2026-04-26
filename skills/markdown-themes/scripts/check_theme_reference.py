#!/usr/bin/env python3
"""Check whether theme-reference.md matches CSS assets."""

from __future__ import annotations

import re
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_DIR / "assets"
REFERENCE = SKILL_DIR / "references" / "theme-reference.md"


def normalize(name: str) -> str:
    return name.removesuffix(".css").lower()


def main() -> int:
    asset_names = {
        normalize(path.stem)
        for path in ASSETS_DIR.glob("*.css")
    }
    text = REFERENCE.read_text(encoding="utf-8")
    documented_names = {
        normalize(match.group(1))
        for match in re.finditer(r"^### `([^`]+)`", text, flags=re.MULTILINE)
    }

    missing = sorted(asset_names - documented_names)
    orphaned = sorted(documented_names - asset_names)

    if not missing and not orphaned:
        print("theme-reference.md covers all CSS themes.")
        return 0

    if missing:
        print("Missing in theme-reference.md:")
        for name in missing:
            print(f"- {name}")
    if orphaned:
        print("Documented but CSS not found:")
        for name in orphaned:
            print(f"- {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
