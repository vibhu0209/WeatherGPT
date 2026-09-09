import re
from pathlib import Path

content = Path(r"d:\WeatherGPT\android\app\src\main\res\values\strings.xml").read_text(encoding="utf-8")
keys = re.findall(r'name="([^"]+)"', content)
print(len(keys))
for k in keys:
    print(k)
