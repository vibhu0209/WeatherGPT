p = r"d:\WeatherGPT\android\app\src\main\res\values-te\strings.xml"
lines = open(p, encoding="utf-8").read().splitlines()
out = open(r"d:\WeatherGPT\scripts\te_debug.txt", "w", encoding="utf-8")
for i in [56, 71, 82, 114, 120]:
    out.write(f"{i+1} {repr(lines[i])}\n")
out.close()
