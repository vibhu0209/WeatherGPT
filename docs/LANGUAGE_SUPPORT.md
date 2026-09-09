# Language support

The app has Android string resources for all 11 requested language identifiers: en, hi, bn, te, mr, ta, gu, kn, ml, pa, or. English and Hindi currently cover all fixed UI text; other languages cover 25 core controls and fall back to English for longer explanations. Complete translations and native-speaker review remain required; do not label these nine languages fully supported.

Online deterministic drafts: English and Hindi. BHASHINI and Google Cloud Translation adapters can translate verified English drafts into the other configured UI languages; both are disabled without backend credentials, and failure keeps the English text. Numeric preservation is validated before translated text is returned. Free-text intent understanding outside English/Hindi remains limited. The app explains this in Settings. Speech input delegates to the installed Android recognizer activity, provides the selected language tag, and returns editable text before sending. Availability and offline capability depend on the installed engine. Playback checks installed TTS support and reports failure without crashing. No raw audio is stored by WeatherGPT.

Offline chat currently answers in English and Hindi and explicitly labels the cached forecast. External translation needs connectivity. BHASHINI and Google translation request contracts are fixture-tested but not live-tested because credentials are absent. Their absence does not block typing, reading or Android speech on supported phones.

