#!/usr/bin/env python3
"""Build complete locale_strings_data.py."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "android/app/src/main/res/values/strings.xml"
OUT = Path(__file__).resolve().parent / "locale_strings_data.py"

KEYS = re.findall(r'name="([^"]+)"', MASTER.read_text(encoding="utf-8"))


def parse_xml(locale: str) -> dict[str, str]:
    path = ROOT / f"android/app/src/main/res/values-{locale}/strings.xml"
    if not path.exists():
        return {}
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    return {el.attrib["name"]: el.text or "" for el in root.findall("string")}


def fix_te(table: dict[str, str]) -> None:
    table["research"] = "పరిశోధన / iklim"
    table["show_details"] = "ఎందuk? వాతావరణ వివరాలు చూడండి"
    table["spray_question"] = "రేపు వర్షం లేదా గాలితో పంట పితikiకi ప్రభావం ఉంటుందా?"


# fmt: off
MR: dict[str, str] = {
    "chat": "विचारा",
    "forecast": "हवामान",
    "home": "होम",
    "home_intro": "तुमचे हवामान, स्कोर आणि उपयुक्त सल्ला एकाच ठिकाणी.",
    "weather_score": "पुढील 24 तासांचा हवामान स्कोर",
    "your_advice": "तुमच्यासाठी सल्ला",
    "score_disclaimer": "हे अधिकृत सुरक्षा प्रमाणपत्र नाही. कृती करण्यापूर्वी अधिकृत इशारे पहा.",
    "hourly": "तास तासाने",
    "alerts": "इशारे",
    "settings": "सेटिंग्ज",
    "choose_place": "तुमचे ठिकाण निवडा",
    "welcome_tag": "दररोजचा हवामान साथी",
    "welcome": "नमस्कार! मी कशी मदत करू?",
    "intro": "हवामानाबद्दल तुमच्या शब्दांत विचारा. लिहा किंवा बोला. खाते लागत नाही.",
    "rain_question": "आज पाऊस पडेल का?",
    "tomorrow_question": "उद्या हवामान कसे असेल?",
    "warning_question": "हवामानाचे इशारे आहेत का?",
    "climate_question": "गेल्या 10 वर्षांत हे ठिकाण अधिक उबदार झाले का?",
    "you": "तुम्ही",
    "listen": "ऐका",
    "speak": "बोला",
    "send": "पाठवा",
    "type_question": "हवामानाबद्दल विचारा",
    "voice_unavailable": "या फोनवर किंवा या भाषेत आवाज उपलब्ध नाही. तुम्ही प्रश्न लिहू शकता.",
    "saved_notice": "जतन केलेले हवामान — परिस्थिती बदलू शकते. नवीन माहितीसाठी इंटरनेटला जोडा.",
    "loading": "हवामान माहिती येत आहे",
    "updated": "डाउनलोड केले",
    "minutes_ago": "मिनिटांपूर्वी",
    "single_source": "एक हवामान स्रोत उपलब्ध. हा अंदाज आहे, हमी नाही.",
    "disagree": "हवामान स्रोत वेगळे आहेत. योजना बदलावी लागू शकते.",
    "saved_weather": "तुमचा डाउनलोड केलेला अंदाज",
    "no_saved": "अजून हवामान जतन नाही. ठिकाण निवडून अंदाज डाउनलोड करा.",
    "download": "हवामान डाउनलोड / ताजे करा",
    "forecast_help": "पुढील तीन दिवस, तास तासाने. पावसाची शक्यता त्या तासासाठी.",
    "no_places": "ठिकाण सापडले नाही. जवळचे शहर किंवा दुसरी शब्दलेखन पहा.",
    "search_failed": "ठिकाण शोधता आले नाही. इंटरनेट तपासून पुन्हा प्रयत्न करा.",
    "refresh_failed": "नवीन हवामान मिळाले नाही. आधी डाउनलोड केलेले उपलब्ध राहील.",
    "place_help": "तुमचे गाव, कसबा किंवा शहर शोधा. लोकेशन परवानगी लागत नाही.",
    "city_village": "गाव, कसबा किंवा शहर",
    "saved_places": "जतन केलेली ठिकाणे",
    "search": "ठिकाण शोधा",
    "close": "बंद करा",
    "alert_unknown": "अधिकृत इशारा सेवा अजून जोडलेली नाही.",
    "alert_help": "याचा अर्थ इशारे नाहीत असा नाही. बाहेर जाण्यापूर्वी तुमच्या भागाचे IMD इशारे पहा.",
    "offline_alerts": "इंटरनेटशिवाय या फोनवर नवीन हवामान इशारे मिळत नाहीत.",
    "open_imd": "अधिकृत IMD वेबसाइट उघडा",
    "risk_estimates": "WeatherGPT धोका अंदाज",
    "risk_help": "हे अंदाजातील मूल्यांवरून काढले आहेत. सरकारी इशार्यांपेक्षा वेगळे.",
    "no_risk_estimates": "डाउनलोड अंदाजात स्थानिक धoka मर्यादा ओलांडली नाही. तरीही अधिकृत इशारे पहा.",
    "weather_risk": "WeatherGPT धोका अंदाज",
    "temperature": "तापमान",
    "rain": "पावसाची शक्यता",
    "wind": "वारा",
    "unavailable": "उपलब्ध नाही",
    "sources": "हवामान स्रोत",
    "feels_like": "जाणवते",
    "humidity": "आर्द्रता",
    "gusts": "वाऱ्याचे झोते",
    "visibility": "दृश्यता",
    "uv": "UV निर्देशांक",
    "forecast_confidence": "अंदाज विश्वास",
    "confidence_help": "स्रोत उपलब्धता आणि सहमती दाखवते. अंदाज बरोबर असण्याची शक्यता नाही.",
    "settings_intro": "WeatherGPT तुमच्या सोयीनुसार बदला. तुमची निवड या फोनवर जतन होते.",
    "theme": "स्वरूप",
    "system_theme": "फोनप्रमाणे",
    "light_theme": "फिकट",
    "dark_theme": "गडद",
    "large_text": "मोठी अक्षरे",
    "language": "तुमची भाषा",
    "language_help": "मुख्य बटणे भाषांतरित. सविस्तर उत्तरे सध्या मराठी, हिंदी किंवा इंग्रजीत. आवाज फोनवर अवलंबून.",
    "use_for": "तुम्हाला हवामान माहिती कशासाठी हवी?",
    "general": "दैनंदिन जीवन / शाळा",
    "farming": "शेती",
    "fishing": "मासेमारी",
    "outdoor": "बाहेर काम किंवा प्रवास",
    "tourism": "पर्यटन / प्रवास",
    "transport": "वाहतूक / वितरण",
    "construction": "बांधकाम / बाहेर काम",
    "emergency": "आपत्काल / आपत्ती प्रतिसाद",
    "vendor": "रस्त्यावरील विक्रेता / बाहेर व्यवसाय",
    "aviation": "विमान / व्यावसायिक हवामान",
    "research": "संशोधन / iklim",
    "past_conversations": "मागील संभाषणे",
    "continue_chat": "हे संभाषण सुरू ठेवा",
    "delete_conversation": "हे संभाषण हटवा",
    "no_conversations": "अजून जतन केलेली संभाषणे नाहीत.",
    "new_chat": "चॅट साफ करून पुन्हा सुरू करा",
    "clear_data": "सर्व जतन डेटा हटवा",
    "clear_help": "या फोनवरून चॅट, हवामान, ठिकाण आणि निवड हटवायची?",
    "delete": "हटवा",
    "cancel": "रद्द करा",
    "connection_settings": "कनेक्शन सेटिंग्ज",
    "server_help": "स्थानिक सेटअप: WeatherGPT सर्व्हर पत्ता लिहा, शेवटी / ठेवा. एमुलेटरवर http://10.0.2.2:8000/ वापरा.",
    "save": "जतन करा",
    "wifi_only": "Wi-Fi वरच पार्श्वभूमीत डाउनलोड",
    "risk_notifications": "WeatherGPT धoka अंदाजाची सूचना",
    "risk_notification_help": "डाउनलोड अंदाजावरून गणना. हे अधिकृत इशारे नाहीत.",
    "official_warning": "अधिकृत हवामान इशारा",
    "expires": "समाप्ती",
    "official_notifications": "अधिकृत हवामान इशaraची सूचना",
    "official_notification_help": "विश्वसनीय सरकारी फीड जोडली असेल आणि फोन रिफ्रेश करू शकेल तेव्हाच काम करते.",
    "clear_sky": "स्वच्छ आकाश",
    "cloudy": "ढगाळ",
    "fog": "धुके",
    "drizzle": "हलका रिमझिम",
    "rainy": "पाऊस",
    "snow": "बर्फ",
    "showers": "सरी",
    "thunderstorm": "वादळ",
    "use_current_location": "माझे सध्याचे ठिकाण वापरा",
    "current_location": "सध्याचे ठिकाण",
    "location_optional": "ऐच्छिक. तुम्ही गाव किंवा शहर शोधू शकता.",
    "location_unavailable": "सध्याचे ठिकाण उपलब्ध नाही. तुमचे गाव किंवा शहर शोधा.",
    "show_details": "का? हवामान तपशील पहा",
    "hide_details": "हवामान तपशील लपवा",
    "expired_hidden": "काही डाउनलोड इशारे संपले आणि लपवले.",
    "sending_question": "तुमचा प्रश्न पाठवत आहे",
    "checking_sources": "खात्री केलेले हवामान स्रोत तपासत आहे",
    "farm_work_question": "उद्या सकाळी शेताच्या कामासाठी चांगले?",
    "spray_question": "उद्या पाऊस किंवा वara फवaranysa परिणाम करेल का?",
    "marine_question": "मासेमारीसाठी समुद्राची स्थिती कशी?",
    "wave_question": "मासेमारीसाठी समुद्राच्या लाटांची उंची किती?",
    "next_hours_question": "पुढील तीन तास हवामान कसे?",
}
# fmt: on

LOCALE_STRINGS = {"te": parse_xml("te"), "mr": MR}
fix_te(LOCALE_STRINGS["te"])

# Fix mr typos
MR["research"] = "संशोधन / iklim"
MR["no_risk_estimates"] = MR["no_risk_estimates"].replace("धoka", "धोका")
MR["risk_notifications"] = MR["risk_notifications"].replace("धoka", "धोका")
MR["official_notifications"] = "अधिकृत हवामान इशार्याची सूचना"
MR["spray_question"] = "उद्या पाऊस किंवा वara फवarnyasathi परिणाम करेल का?"
