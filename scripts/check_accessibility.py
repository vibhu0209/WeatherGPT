"""Check resource references and WCAG text contrast of the two explicit palettes.

Run from the repository root: python scripts/check_accessibility.py
"""
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

SOURCE_DIR = Path('android/app/src/main/java/in/weathergpt')
STRINGS = Path('android/app/src/main/res/values/strings.xml')
PALETTES = {'WeatherLight': 'Light', 'WeatherDark': 'Dark'}
PAIRS = [
    ('onPrimary', 'primary'),
    ('onSurface', 'surface'),
    ('onSurfaceVariant', 'surfaceVariant'),
    ('onPrimaryContainer', 'primaryContainer'),
    ('onSecondaryContainer', 'secondaryContainer'),
    ('onTertiaryContainer', 'tertiaryContainer'),
    ('onErrorContainer', 'errorContainer'),
]
NAMED_COLORS = {'Color.White': 'FFFFFF', 'Color.Black': '000000'}

failures: list[str] = []

# 1. Every R.string reference in Kotlin source must exist in the default string pack.
keys = {element.attrib['name'] for element in ET.parse(STRINGS).getroot()}
sources = sorted(SOURCE_DIR.glob('*.kt'))
if not sources:
    sys.exit(f'No Kotlin sources found under {SOURCE_DIR}')
for path in sources:
    missing = sorted(set(re.findall(r'R\.string\.(\w+)', path.read_text(encoding='utf-8'))) - keys)
    if missing:
        failures.append(f'{path.name}: missing string resources {missing}')
print(f'Checked R.string references in {len(sources)} Kotlin files against {len(keys)} default strings')


def luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def palette_colours(text: str, name: str) -> dict[str, str]:
    """Read one `val <name> = lightColorScheme(...)` / `darkColorScheme(...)` block."""
    match = re.search(rf'\bval\s+{name}\s*=\s*\w+ColorScheme\s*\(', text)
    if not match:
        return {}
    index, depth = match.end(), 1
    while index < len(text) and depth:
        depth += {'(': 1, ')': -1}.get(text[index], 0)
        index += 1
    block = text[match.end():index - 1]
    colours = dict(re.findall(r'(\w+)\s*=\s*Color\(0x[Ff][Ff]([0-9A-Fa-f]{6})\)', block))
    for token, value in NAMED_COLORS.items():
        colours.update({key: value for key in re.findall(rf'(\w+)\s*=\s*{re.escape(token)}', block)})
    return {key: value.upper() for key, value in colours.items()}


# 2. Both explicit palettes must clear WCAG AA (4.5:1) on every text/background pair.
theme_text = '\n'.join(path.read_text(encoding='utf-8') for path in sources)
checked = 0
for symbol, label in PALETTES.items():
    colours = palette_colours(theme_text, symbol)
    if not colours:
        failures.append(f'{label}: palette `{symbol}` not found in {SOURCE_DIR}')
        continue
    for foreground, background in PAIRS:
        if foreground not in colours or background not in colours:
            failures.append(f'{label}: pair {foreground}/{background} is not defined explicitly')
            continue
        low, high = sorted((luminance(colours[foreground]), luminance(colours[background])))
        ratio = (high + 0.05) / (low + 0.05)
        checked += 1
        print(f'{label} {foreground} on {background}: {ratio:.2f}:1')
        if ratio < 4.5:
            failures.append(f'{label}: {foreground} on {background} is {ratio:.2f}:1, below 4.5:1')

if failures:
    print('\nAccessibility check FAILED:')
    for failure in failures:
        print(f'  - {failure}')
    sys.exit(1)
print(f'\nTheme contrast ({checked} pairs) and resource references passed')
