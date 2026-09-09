from pathlib import Path

extras = {
    "onboard_intro": {
        "en": "A few quick choices so WeatherGPT fits how you use weather.",
        "hi": "कुछ सरल विकल्प, ताकि WeatherGPT आपके मौसम के उपयोग के अनुसार रहे।",
    },
    "onboard_next": {"en": "Continue", "hi": "आगे बढ़ें"},
    "onboard_back": {"en": "Back", "hi": "पीछे"},
    "onboard_finish": {"en": "Start using WeatherGPT", "hi": "WeatherGPT शुरू करें"},
    "occupation_help": {
        "en": "This changes your weather score, advice and chat suggestions. You can change it later in Settings.",
        "hi": "इससे आपका मौसम स्कोर, सलाह और चैट सुझाव बदलते हैं। बाद में सेटिंग्स में बदल सकते हैं।",
    },
    "theme_help": {
        "en": "Choose light, dark, or follow your phone. Larger text helps readability.",
        "hi": "हल्का, गहरा, या फ़ोन के अनुसार चुनें। बड़ा टेक्स्ट पढ़ने में मदद करता है।",
    },
    "permissions_title": {"en": "Location and notifications", "hi": "स्थान और सूचनाएँ"},
    "permissions_help": {
        "en": "WeatherGPT needs approximate location to load your weather. Notifications are optional for warnings and local risk estimates.",
        "hi": "आपका मौसम लाने के लिए अनुमानित स्थान चाहिए। चेतावनी और स्थानीय जोखिम के लिए सूचनाएँ वैकल्पिक हैं।",
    },
    "grant_location": {"en": "Allow location", "hi": "स्थान की अनुमति दें"},
    "grant_notifications": {"en": "Allow notifications", "hi": "सूचनाओं की अनुमति दें"},
    "locating": {"en": "Finding your location…", "hi": "आपका स्थान खोजा जा रहा है…"},
    "location_preferred": {
        "en": "We use your phone location first. Search is only a backup if GPS is unavailable.",
        "hi": "पहले फ़ोन का स्थान उपयोग होता है। GPS न मिले तो ही खोज बैकअप है।",
    },
    "search_place_fallback": {"en": "Search village or city instead", "hi": "बजाय गाँव या शहर खोजें"},
    "skip_for_now": {"en": "Skip for now", "hi": "अभी छोड़ें"},
    "personalization": {"en": "Personalize WeatherGPT", "hi": "WeatherGPT को अपने अनुसार बनाएँ"},
    "step_of": {"en": "Step %1$d of %2$d", "hi": "चरण %1$d / %2$d"},
    "permissions_granted": {"en": "Allowed", "hi": "अनुमति मिली"},
    "permissions_needed": {"en": "Not allowed yet", "hi": "अभी अनुमति नहीं"},
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
        print(loc, "+", len(additions))
    else:
        print(loc, "ok")

# Prefer device location wording
en = res / "values" / "strings.xml"
et = en.read_text(encoding="utf-8")
et = et.replace(
    "Optional. You can keep using village or city search instead.",
    "We prefer your phone location. Search is only if GPS is unavailable.",
)
en.write_text(et, encoding="utf-8")
print("location_optional updated")
