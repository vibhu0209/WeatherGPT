#!/usr/bin/env python3
"""Generate complete locale strings.xml files from translation tables."""
from __future__ import annotations

import re
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "android" / "app" / "src" / "main" / "res"
MASTER = RES / "values" / "strings.xml"

LOCALES = {
    "bn": RES / "values-bn" / "strings.xml",
    "te": RES / "values-te" / "strings.xml",
    "mr": RES / "values-mr" / "strings.xml",
    "ta": RES / "values-ta" / "strings.xml",
    "gu": RES / "values-gu" / "strings.xml",
    "kn": RES / "values-kn" / "strings.xml",
    "ml": RES / "values-ml" / "strings.xml",
    "pa": RES / "values-pa" / "strings.xml",
    "or": RES / "values-or" / "strings.xml",
}

# fmt: off
TRANSLATIONS: dict[str, dict[str, str]] = {
"bn": {
    "chat": "জিজ্ঞাসা",
    "forecast": "আবহাওয়া",
    "home": "হোম",
    "home_intro": "আপনার আবহাওয়া, স্কোর ও কাজের совет এক জায়গায়।",
    "weather_score": "আগামী ২৪ ঘণ্টার আবহাওয়া স্কোর",
    "your_advice": "আপনার জন্য পরামর্শ",
    "score_disclaimer": "এটি সরকারি নিরাপত্তা সনদ নয়। কাজ করার আগে সরকারি সতর্কতা দেখুন।",
    "hourly": "ঘণ্টা অনুযায়ী",
    "alerts": "সতর্কতা",
    "settings": "সেটিংস",
    "choose_place": "আপনার স্থান বাছুন",
    "welcome_tag": "প্রতিদিনের আবহাওয়া সঙ্গী",
    "welcome": "নমস্কার! কীভাবে সাহায্য করব?",
    "intro": "আবহাওয়া সম্পর্কে নিজের ভাষায় জিজ্ঞাসা করুন। লিখতে বা বলতে পারেন। অ্যাকাউন্ট লাগবে না।",
    "rain_question": "আজ কি বৃষ্টি হবে?",
    "tomorrow_question": "আগামীকাল আবহাওয়া কেমন?",
    "warning_question": "আবহাওয়ার সতর্কতা আছে কি?",
    "climate_question": "গত ১০ বছরে এই জায়গা কি গরম হয়েছে?",
    "you": "আপনি",
    "listen": "শুনুন",
    "speak": "বলুন",
    "send": "পাঠান",
    "type_question": "আবহাওয়া সম্পর্কে জিজ্ঞাসা করুন",
    "voice_unavailable": "এই ফোন বা ভাষায় কণ্ঠস্বর নেই। তবু প্রশ্ন লিখতে পারেন।",
    "saved_notice": "সংরক্ষিত আবহাওয়া — অবস্থা বদলাতে পারে। নতুন তথ্যের জন্য ইন্টারনেটে যুক্ত হোন।",
    "loading": "আবহাওয়ার তথ্য আসছে",
    "updated": "ডাউনলোড হয়েছে",
    "minutes_ago": "মিনিট আগে",
    "single_source": "একটি আবহাওয়া উৎস আছে। এটি পূর্বাভাস, গ্যারান্টি নয়।",
    "disagree": "আবহাওয়া উৎসগুলো মিলছে না। পরিকল্পনা বদলাতে হতে পারে।",
    "saved_weather": "আপনার ডাউনলোড করা পূর্বাভাস",
    "no_saved": "এখনও আবহাওয়া সংরক্ষিত নেই। স্থান বেছে পূর্বাভাস ডাউনলোড করুন।",
    "download": "আবহাওয়া ডাউনলোড / নবায়ন",
    "forecast_help": "আগামী তিন দিন, ঘণ্টা অনুযায়ী। বৃষ্টির সম্ভাবনা সেই ঘণ্টার জন্য।",
    "no_places": "স্থান পাওয়া যায়নি। কাছের শহর বা অন্য বানান চেষ্টা করুন।",
    "search_failed": "স্থান খোঁজা যায়নি। ইন্টারনেট দেখে আবার চেষ্টা করুন।",
    "refresh_failed": "নতুন আবহাওয়া পাওয়া যায়নি। আগে ডাউনলোড করা তথ্য থাকলে থাকবে।",
    "place_help": "গ্রাম, শহর বা নগর খুঁজুন। লোকেশন অনুমতি লাগবে না।",
    "city_village": "গ্রাম, শহর বা নগর",
    "saved_places": "সংরক্ষিত স্থান",
    "search": "স্থান খুঁজুন",
    "close": "বন্ধ করুন",
    "alert_unknown": "সরকারি সতর্কতা সেবা এখনও যুক্ত নয়।",
    "alert_help": "এর মানে সতর্কতা নেই তা নয়। বাইরে যাওয়ার আগে আপনার এলাকার IMD সতর্কতা দেখুন।",
    "offline_alerts": "ইন্টারনেট ছাড়া ফোনে নতুন আবহাওয়া সতর্কতা পাওয়া যায় না।",
    "open_imd": "সরকারি IMD ওয়েবসাইট খুলুন",
    "risk_estimates": "WeatherGPT ঝুঁকি অনুমান",
    "risk_help": "এগুলো পূর্বাভাসের মান থেকে বের করা। সরকারি সতর্কতা থেকে আলাদা।",
    "no_risk_estimates": "ডাউনলোড করা পূর্বাভাসে স্থানীয় ঝুঁকি সীমা পার হয়নি। তবু সরকারি সতর্কতা দেখুন।",
    "weather_risk": "WeatherGPT ঝুঁকি অনুমান",
    "temperature": "তাপমাত্রা",
    "rain": "বৃষ্টির সম্ভাবনা",
    "wind": "বাতাস",
    "unavailable": "উপলব্ধ নয়",
    "sources": "আবহাওয়া উৎস",
    "feels_like": "অনুভূত তাপ",
    "humidity": "আর্দ্রতা",
    "gusts": "দমকা হাওয়া",
    "visibility": "দৃশ্যমানতা",
    "uv": "ইউভি সূচক",
    "forecast_confidence": "পূর্বাভাসে বিশ্বাস",
    "confidence_help": "উৎসের উপলব্ধতা ও মিল বোঝায়। পূর্বাভাস সঠিক হওয়ার সম্ভাবনা নয়।",
    "settings_intro": "WeatherGPT আপনার সুবিধামতো সাজান। পছন্দ এই ফোনে সংরক্ষিত হয়।",
    "theme": "চেহারা",
    "system_theme": "ফোন অনুযায়ী",
    "light_theme": "হালকা",
    "dark_theme": "গাঢ়",
    "large_text": "বড় লেখা",
    "language": "আপনার ভাষা",
    "language_help": "মূল বোতাম অনুবাদিত। বিস্তারিত উত্তর এখন বাংলা, হিন্দি বা ইংরেজিতে। কণ্ঠস্বর ফোনের উপর নির্ভর করে।",
    "use_for": "আবহাওয়া তথ্য কিসের জন্য চান?",
    "general": "দৈনন্দিন জীবন / স্কুল",
    "farming": "কৃষিকাজ",
    "fishing": "মাছ ধরা",
    "outdoor": "বাইরে কাজ বা ভ্রমণ",
    "tourism": "পর্যটন / ভ্রমণ",
    "transport": "পরিবহন / ডেলিভারি",
    "construction": "নির্মাণ / বাইরের শ্রম",
    "emergency": "জরুরি / দুর্যোগ প্রতিক্রিয়া",
    "vendor": "রাস্তার বিক্রেতা / বাইরের ব্যবসা",
    "aviation": "বিমান / পেশাদার আবহাওয়া",
    "research": "গবেষণা / জলবায়ু",
    "past_conversations": "আগের কথোপকথন",
    "continue_chat": "এই কথোপকথন চালিয়ে যান",
    "delete_conversation": "এই কথোপকথন মুছুন",
    "no_conversations": "এখনও কোনো কথোপকথন সংরক্ষিত নয়।",
    "new_chat": "চ্যাট মুছে আবার শুরু",
    "clear_data": "সব সংরক্ষিত তথ্য মুছুন",
    "clear_help": "এই ফোন থেকে চ্যাট, আবহাওয়া, স্থান ও পছন্দ মুছবেন?",
    "delete": "মুছুন",
    "cancel": "বাতিল",
    "connection_settings": "সংযোগ সেটিংস",
    "server_help": "স্থানীয় সেটআপ: WeatherGPT সার্ভারের ঠিকানা লিখুন, শেষে / দিন। এমুলেটরে http://10.0.2.2:8000/ ব্যবহার করুন।",
    "save": "সংরক্ষণ",
    "wifi_only": "শুধু Wi-Fi-তে পটভূমিতে ডাউনলোড",
    "risk_notifications": "WeatherGPT ঝুঁকি অনুমানের বিজ্ঞপ্তি",
    "risk_notification_help": "ডাউনলোড করা পূর্বাভাস থেকে হিসাব। এগুলো সরকারি সতর্কতা নয়।",
    "official_warning": "সরকারি আবহাওয়া সতর্কতা",
    "expires": "মেয়াদ শেষ",
    "official_notifications": "সরকারি আবহাওয়া সতর্কতার বিজ্ঞপ্তি",
    "official_notification_help": "বিশ্বস্ত সরকারি ফিড যুক্ত ও ফোন আপডেট করতে পারলে কাজ করে।",
    "clear_sky": "পরিষ্কার আকাশ",
    "cloudy": "মেঘলা",
    "fog": "কুয়াশা",
    "drizzle": "হালকা গুঁড়ি গুঁড়ি বৃষ্টি",
    "rainy": "বৃষ্টি",
    "snow": "তুষার",
    "showers": "ঝরঝরে বৃষ্টি",
    "thunderstorm": "বজ্রবৃষ্টি",
    "use_current_location": "আমার বর্তমান স্থান ব্যবহার",
    "current_location": "বর্তমান স্থান",
    "location_optional": "ঐচ্ছিক। গ্রাম বা শহর খুঁজেও ব্যবহার করতে পারেন।",
    "location_unavailable": "বর্তমান স্থান পাওয়া যায়নি। গ্রাম বা শহর খুঁজুন।",
    "show_details": "কেন? আবহাওয়ার বিস্তারিত দেখুন",
    "hide_details": "আবহাওয়ার বিস্তারিত লুকান",
    "expired_hidden": "কিছু ডাউনলোড করা সতর্কতার মেয়াদ শেষ, লুকানো হয়েছে।",
    "sending_question": "আপনার প্রশ্ন পাঠানো হচ্ছে",
    "checking_sources": "যাচাইকৃত আবহাওয়া উৎস দেখছি",
    "farm_work_question": "আগামীকাল সকালে খামারের কাজের জন্য ভালো?",
    "spray_question": "আগামীকাল বৃষ্টি বা বাতাস ফসল স্প্রে-এ প্রভাব ফেলবে?",
    "marine_question": "মাছ ধরার জন্য সমুদ্রের অবস্থা কেমন?",
    "wave_question": "মাছ ধরার জন্য সমুদ্রের ঢেউ কত উঁচু?",
    "next_hours_question": "আগামী তিন ঘণ্টায় আবহাওয়া কেমন?",
},
}
# fmt: on

def master_keys() -> list[str]:
    content = MASTER.read_text(encoding="utf-8")
    return re.findall(r'name="([^"]+)"', content)


def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("'", "\\'")
        .replace('"', '\\"')
    )


def write_locale(locale: str, path: Path, keys: list[str], table: dict[str, str]) -> int:
    missing = [k for k in keys if k not in table]
    if missing:
        raise SystemExit(f"{locale}: missing {len(missing)} keys: {missing[:5]}...")
    lines = ["<resources>"]
    for key in keys:
        value = table[key].replace("'", "\\'")
        lines.append(f'    <string name="{key}">{value}</string>')
    lines.append("</resources>")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(keys)


def main() -> None:
    keys = master_keys()
    for locale, path in LOCALES.items():
        if locale not in TRANSLATIONS:
            raise SystemExit(f"No translations for {locale}")
        count = write_locale(locale, path, keys, TRANSLATIONS[locale])
        print(f"{path.name} ({locale}): {count} keys")


if __name__ == "__main__":
    main()
