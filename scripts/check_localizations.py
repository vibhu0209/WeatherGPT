#!/usr/bin/env python3
"""Validate Android localization coverage without generating translations."""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "android" / "app" / "src" / "main" / "res"
FULL_LOCALES = {"hi", "bn", "te", "mr", "ta", "gu", "kn", "ml", "pa", "or"}
CORE_KEYS = {
    "chat", "forecast", "alerts", "settings", "choose_place", "listen", "speak", "send",
    "search", "close", "theme", "light_theme", "dark_theme", "large_text", "language",
    "general", "farming", "fishing", "outdoor", "temperature", "rain", "wind",
}
PLACEHOLDER = re.compile(r"%(?:\d+\$)?[-#+ 0,(<]*\d*(?:\.\d+)?[a-zA-Z%]")


def read_strings(path: Path) -> tuple[dict[str, str], list[str]]:
    root = ET.parse(path).getroot()
    nodes = root.findall("string")
    names = [node.attrib["name"] for node in nodes]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    return {node.attrib["name"]: "".join(node.itertext()) for node in nodes}, duplicates


def main() -> int:
    master, duplicates = read_strings(RES / "values" / "strings.xml")
    errors: list[str] = []
    if duplicates:
        errors.append(f"values: duplicate keys: {duplicates}")
    reports = [f"en: {len(master)}/{len(master)}"]
    for path in sorted(RES.glob("values-*/strings.xml")):
        locale = path.parent.name.removeprefix("values-")
        values, locale_duplicates = read_strings(path)
        missing = set(master) - set(values)
        unknown = set(values) - set(master)
        required = set(master) if locale in FULL_LOCALES else CORE_KEYS
        required_missing = required - set(values)
        placeholder_mismatch = sorted(
            key for key in set(master) & set(values)
            if PLACEHOLDER.findall(master[key]) != PLACEHOLDER.findall(values[key])
        )
        if locale_duplicates:
            errors.append(f"{locale}: duplicate keys: {locale_duplicates}")
        if unknown:
            errors.append(f"{locale}: unknown keys: {sorted(unknown)}")
        if required_missing:
            errors.append(f"{locale}: required keys missing: {sorted(required_missing)}")
        if placeholder_mismatch:
            errors.append(f"{locale}: placeholder mismatch: {placeholder_mismatch}")
        reports.append(f"{locale}: {len(master)-len(missing)}/{len(master)}")
    print("Localization coverage: " + ", ".join(reports))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Localization integrity and required coverage passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
