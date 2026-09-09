import re
import pathlib

root = pathlib.Path(r"D:/WeatherGPT/android/app/src/main/res")
files = sorted(root.glob("values*/strings.xml"))


def keys(p: pathlib.Path) -> set[str]:
    text = p.read_text(encoding="utf-8")
    return set(re.findall(r'<string name="([^"]+)"', text))


def values_map(p: pathlib.Path) -> dict[str, str]:
    text = p.read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for m in re.finditer(r'<string name="([^"]+)">(.*?)</string>', text, re.S)}


base = keys(root / "values" / "strings.xml")
base_map = values_map(root / "values" / "strings.xml")
print(f"values: {len(base)} keys")
for f in files:
    k = keys(f)
    folder = f.parent.name
    if folder == "values":
        continue
    missing = sorted(base - k)
    extra = sorted(k - base)
    print(f"{folder}: {len(k)} keys | missing={len(missing)} | extra={len(extra)}")
    if missing:
        print("  missing:", ", ".join(missing))
    if extra:
        print("  extra:", ", ".join(extra))

print("\nIdentical-to-English counts:")
for folder in [
    "values-hi",
    "values-bn",
    "values-te",
    "values-mr",
    "values-ta",
    "values-gu",
    "values-kn",
    "values-ml",
    "values-pa",
    "values-or",
]:
    m = values_map(root / folder / "strings.xml")
    identical = sorted(name for name, val in m.items() if name in base_map and val == base_map[name])
    print(f"{folder}: {len(identical)} identical")
    if identical:
        print(" ", ", ".join(identical))
