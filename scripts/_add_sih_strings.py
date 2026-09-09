from pathlib import Path

extras = {
    "alerts_none_active": {
        "en": "No active official warning in the connected feed for this place. Refresh before going out.",
        "hi": "जुड़ी सेवा में इस स्थान के लिए कोई सक्रिय आधिकारिक चेतावनी नहीं मिली। बाहर जाने से पहले फिर जाँचें।",
    },
    "home_alerts": {"en": "Alerts", "hi": "चेतावनियाँ"},
    "compare_place": {"en": "Compare with another saved place", "hi": "किसी और सहेजे स्थान से तुलना करें"},
    "compare_with": {"en": "Compare with %1$s", "hi": "%1$s से तुलना करें"},
    "place_purpose": {"en": "How will you use this place?", "hi": "इस स्थान का उपयोग कैसे करेंगे?"},
    "purpose_home": {"en": "Home", "hi": "घर"},
    "purpose_farm": {"en": "Farm", "hi": "खेत"},
    "purpose_harbour": {"en": "Harbour / fishing", "hi": "बंदरगाह / मछली"},
    "purpose_work": {"en": "Work site", "hi": "कार्यस्थल"},
    "action_hourly": {"en": "Show hourly forecast", "hi": "घंटेवार पूर्वानुमान दिखाएँ"},
    "action_warnings": {"en": "Check warnings", "hi": "चेतावनी देखें"},
    "action_score": {"en": "Weather score for me", "hi": "मेरे लिए मौसम स्कोर"},
    "no_active_official": {
        "en": "Connected feed reports no active official warning here.",
        "hi": "जुड़ी सेवा यहाँ कोई सक्रिय आधिकारिक चेतावनी नहीं बताती।",
    },
    "clearing_compare": {"en": "Clear compare place", "hi": "तुलना स्थान हटाएँ"},
}

locales = ["en", "hi", "bn", "te", "mr", "ta", "gu", "kn", "ml", "pa", "or"]
res = Path(r"D:\WeatherGPT\android\app\src\main\res")
for loc in locales:
    path = res / ("values" if loc == "en" else f"values-{loc}") / "strings.xml"
    text = path.read_text(encoding="utf-8")
    additions = []
    for key, table in extras.items():
        if f'name="{key}"' in text:
            continue
        value = (table.get(loc) or table["en"]).replace("'", "\\'")
        additions.append(f'    <string name="{key}">{value}</string>')
    if additions:
        text = text.replace("</resources>", "\n".join(additions) + "\n</resources>\n")
        path.write_text(text, encoding="utf-8")
        print(loc, "added", len(additions))
    else:
        print(loc, "ok")

en = res / "values" / "strings.xml"
et = en.read_text(encoding="utf-8")
old = "Core controls are translated. Detailed answers currently use English or Hindi. Voice depends on your phone."
new = "Core controls are translated in all 11 languages. Online chat answers use English or Hindi first. Offline answers use your language when available. Voice depends on your phone."
if old in et:
    en.write_text(et.replace(old, new), encoding="utf-8")
    print("language_help updated")
else:
    print("language_help already changed or missing")
