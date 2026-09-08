# Language support

The app has Android string resources for all 11 requested language identifiers: en, hi, bn, te, mr, ta, gu, kn, ml, pa, or. English and Hindi currently cover all fixed UI text; other languages cover 25 core controls and fall back to English for longer explanations. Complete translations and native-speaker review remain required; do not label these nine languages fully supported.

Online deterministic answers: English and Hindi. Unsupported-language free-text is not reliably understood. The app explains this in Settings. Speech input delegates to the installed Android recognizer activity, provides the selected language tag, and returns editable text before sending. Availability and offline capability depend on the installed engine. Playback checks installed TTS support and reports failure without crashing. No raw audio is stored by WeatherGPT.

Offline chat currently answers in English and Hindi and explicitly labels the cached forecast. BHASHINI and Google Cloud translation/ASR/TTS have not been implemented, configured or tested. Their absence does not block typing, reading or Android speech on supported phones.

