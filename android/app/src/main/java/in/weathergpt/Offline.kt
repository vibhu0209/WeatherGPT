package `in`.weathergpt

import java.time.*

enum class FreshnessState { FRESH, AGING, STALE }
object Freshness {
    fun weather(retrievedAt:String,now:Instant=Instant.now()):FreshnessState {
        val minutes=Duration.between(Instant.parse(retrievedAt),now).toMinutes()
        return when { minutes<=60 -> FreshnessState.FRESH; minutes<=180 -> FreshnessState.AGING; else -> FreshnessState.STALE }
    }
    fun officialAlert(retrievedAt:String,expires:String?,now:Instant=Instant.now()):FreshnessState {
        if(expires==null || runCatching{Instant.parse(expires)<=now}.getOrDefault(true)) return FreshnessState.STALE
        return if(Duration.between(Instant.parse(retrievedAt),now).toMinutes()<=15) FreshnessState.FRESH else FreshnessState.AGING
    }
    fun climate(retrievedAt:String,now:Instant=Instant.now())=if(Duration.between(Instant.parse(retrievedAt),now).toDays()<=7) FreshnessState.FRESH else FreshnessState.STALE
}

object Offline {
    private val weatherWords=listOf(
        "weather","rain","temperature","wind","today","tomorrow","morning","evening","afternoon",
        "score","work","sow","spray","irrigat","outdoor","warning","alert","humid",
        "मौसम","बारिश","कल","आज","सुबह","शाम","மாலை","நாளை","மழை","இன்று","வானிலை",
        "ভোর","কাল","বৃষ্টি","আজ","আবহাওয়া","వర్షం","రేపు","ఈరోజు","వాతావరణం",
        "उद्या","पाऊस","हवामान","કાલે","વરસાદ","હવામાન","આજે",
        "ನಾಳೆ","ಮಳೆ","ಹವಾಮಾನ","ಇಂದು","നാളെ","മഴ","കാലാവസ്ഥ","ഇന്ന്",
        "ਕੱਲ੍ਹ","ਮੀਂਹ","ਮੌਸਮ","ਅੱਜ","କାଲି","ବର୍ଷା","ପାଣିପାଗ","ଆଜି"
    )
    private val tomorrowWords=listOf("tomorrow","kal","कल","उद्या","நாளை","কাল","আগামীকাল","రేపు","કાલે","ನಾಳೆ","നാളെ","ਕੱਲ੍ਹ","କାଲି")
    private val todayWords=listOf("today","आज","இன்று","আজ","ఈరోజు","ఈ రోజు","આજે","ಇಂದು","ഇന്ന്","ਅੱਜ","ଆଜି")

    fun answer(text:String,b:BundleDto?,offset:Int,language:String="en"):Pair<String,Int> {
        val q=text.lowercase()
        val lang=normalize(language)
        val day=when {
            tomorrowWords.any { q.contains(it) } -> 1
            todayWords.any { q.contains(it) } -> 0
            else -> offset
        }
        if(b==null) return copy(lang,
            en="No saved forecast yet. Connect to the internet and download your weather first.",
            hi="अभी मौसम सहेजा नहीं गया है। इंटरनेट से जुड़कर पहले मौसम डाउनलोड करें.",
            bn="এখনও কোনো সংরক্ষিত পূর্বাভাস নেই। ইন্টারনেটে যুক্ত হয়ে প্রথমে আবহাওয়া ডাউনলোড করুন।",
            te="ఇంకా సేవ్ చేసిన అంచనా లేదు. ఇంటర్నెట్‌కు కనెక్ట్ అయి ముందు వాతావరణం డౌన్‌లోడ్ చేయండి.",
            mr="अजून जतन अंदाज नाही. इंटरनेटला जोडून आधी हवामान डाउनलोड करा.",
            ta="சேமித்த முன்னறிவு இல்லை. இணையத்துடன் இணைந்து முதலில் வானிலையை பதிவிறக்கவும்.",
            gu="હજુ સાચવેલી આગાહી નથી. ઇન્ટરનેટ જોડીને પહેલાં હવામાન ડાઉનલોડ કરો.",
            kn="ಇನ್ನೂ ಉಳಿಸಿದ ಮುನ್ಸೂಚನೆ ಇಲ್ಲ. ಇಂಟರ್ನೆಟ್ ಸಂಪರ್ಕಿಸಿ ಮೊದಲು ಹವಾಮಾನ ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ.",
            ml="സേവ് ചെയ്ത പ്രവചനം ഇതുവരെ ഇല്ല. ഇന്റർനെറ്റ് ബന്ധിപ്പിച്ച് ആദ്യം കാലാവസ്ഥ ഡൗൺലോഡ് ചെയ്യുക.",
            pa="ਹਾਲੇ ਕੋਈ ਸੰਭਾਲਿਆ ਪੂਰਵ-ਅਨੁਮਾਨ ਨਹੀਂ। ਇੰਟਰਨੈੱਟ ਜੋੜ ਕੇ ਪਹਿਲਾਂ ਮੌਸਮ ਡਾਊਨਲੋਡ ਕਰੋ।",
            or="ଏପର୍ଯ୍ୟନ୍ତ ସଞ୍ଚିତ ପୂର୍ବାନୁମାନ ନାହିଁ। ଇଣ୍ଟରନେଟ୍ ଯୋଡି ପ୍ରଥମେ ପାଣିପାଗ ଡାଉନଲୋଡ୍ କରନ୍ତୁ।",
        ) to day
        val downloaded=Instant.parse(b.retrieved_at).atZone(ZoneId.of(b.location.timezone))
            .format(java.time.format.DateTimeFormatter.ofPattern("d MMM, h:mm a",java.util.Locale.forLanguageTag(speechLocaleTag(lang))))
        val intro=copy(lang,
            en="You're offline. Using the forecast saved at $downloaded.\n\n",
            hi="आप ऑफलाइन हैं। सहेजा मौसम: $downloaded।\n\n",
            bn="আপনি অফলাইন। সংরক্ষিত পূর্বাভাস: $downloaded।\n\n",
            te="మీరు ఆఫ్‌లైన్‌లో ఉన్నారు. సేవ్ చేసిన అంచనా: $downloaded.\n\n",
            ta="நீங்கள் ஆஃப்லைன். சேமித்த முன்னறிவு: $downloaded.\n\n",
            mr="तुम्ही ऑफलाइन आहात. जतन अंदाज: $downloaded.\n\n",
            gu="તમે ઑફલાઇન છો. સાચવેલી આગાહી: $downloaded.\n\n",
            kn="ನೀವು ಆಫ್‌ಲೈನ್. ಉಳಿಸಿದ ಮುನ್ಸೂಚನೆ: $downloaded.\n\n",
            ml="നിങ്ങൾ ഓഫ്‌ലൈനാണ്. സേവ് ചെയ്ത പ്രവചനം: $downloaded.\n\n",
            pa="ਤੁਸੀਂ ਆਫਲਾਈਨ ਹੋ। ਸੰਭਾਲਿਆ ਪੂਰਵ-ਅਨੁਮਾਨ: $downloaded.\n\n",
            or="ଆପଣ ଅଫଲାଇନ୍। ସଞ୍ଚିତ ପୂର୍ବାନୁମାନ: $downloaded.\n\n",
        )
        if(listOf("warning","alert","चेतावनी","সতর্ক","எச்சரிக்கை","హెచ్చరిక","ચેતવણી","ಎಚ್ಚರಿಕೆ","മുന്നറിയിപ്പ്","ਚੇਤਾਵਨੀ","ଚେତାବନୀ").any{q.contains(it)}) {
            val active=b.official_alerts.orEmpty().filter { alert->cachedAlertIsActive(alert) }
            if(active.isNotEmpty()) {
                val warnings=active.joinToString("\n\n") { alert->
                    val instruction=alert.instruction?:alert.description?:""
                    copy(lang,
                        en="Previously downloaded official warning: ${alert.headline}. $instruction Expires: ${alert.expires}.",
                        hi="पहले डाउनलोड की गई आधिकारिक चेतावनी: ${alert.headline}। $instruction समाप्ति: ${alert.expires}.",
                        bn="আগে ডাউনলোড করা সরকারি সতর্কতা: ${alert.headline}। $instruction মেয়াদ: ${alert.expires}.",
                        te="ఇంతకు ముందు డౌన్‌లోడ్ చేసిన అధికారిక హెచ్చరిక: ${alert.headline}. $instruction గడువు: ${alert.expires}.",
                        mr="आधी डाउनलोड केलेला अधिकृत इशारा: ${alert.headline}. $instruction समाप्ती: ${alert.expires}.",
                        ta="முன்பு பதிவிறக்கிய அதிகாரப்பூர்வ எச்சரிக்கை: ${alert.headline}. $instruction காலாவதி: ${alert.expires}.",
                        gu="પહેલાં ડાઉનલોડ થયેલ અધિકૃત ચેતવણી: ${alert.headline}. $instruction સમાપ્તિ: ${alert.expires}.",
                        kn="ಹಿಂದೆ ಡೌನ್‌ಲೋಡ್ ಮಾಡಿದ ಅಧಿಕೃತ ಎಚ್ಚರಿಕೆ: ${alert.headline}. $instruction ಅವಧಿ: ${alert.expires}.",
                        ml="മുമ്പ് ഡൗൺലോഡ് ചെയ്ത ഔദ്യോഗിക മുന്നറിയിപ്പ്: ${alert.headline}. $instruction കാലാവധി: ${alert.expires}.",
                        pa="ਪਹਿਲਾਂ ਡਾਊਨਲੋਡ ਕੀਤੀ ਅਧਿਕਾਰਤ ਚੇਤਾਵਨੀ: ${alert.headline}. $instruction ਸਮਾਪਤੀ: ${alert.expires}.",
                        or="ପୂର୍ବରୁ ଡାଉନଲୋଡ୍ ହୋଇଥିବା ସରକାରୀ ଚେତାବନୀ: ${alert.headline}. $instruction ସମାପ୍ତି: ${alert.expires}.",
                    )
                }
                val needNet=copy(lang,
                    en="New warnings and updates require an internet connection.",
                    hi="नई चेतावनियों और बदलावों के लिए इंटरनेट चाहिए।",
                    bn="নতুন সতর্কতা ও আপডেটের জন্য ইন্টারনেট দরকার।",
                    te="కొత్త హెచ్చరికలు మరియు అప్‌డేట్‌లకు ఇంటర్నెట్ కావాలి.",
                    mr="नवीन इशारे आणि अपडेटसाठी इंटरनेट लागते.",
                    ta="புதிய எச்சரிக்கைகளுக்கும் புதுப்பிப்புகளுக்கும் இணையம் தேவை.",
                    gu="નવી ચેતવણીઓ અને અપડેટ માટે ઇન્ટરનેટ જોઈએ.",
                    kn="ಹೊಸ ಎಚ್ಚರಿಕೆಗಳು ಮತ್ತು ನವೀಕರಣಕ್ಕೆ ಇಂಟರ್ನೆಟ್ ಬೇಕು.",
                    ml="പുതിയ മുന്നറിയിപ്പുകൾക്കും അപ്‌ഡേറ്റുകൾക്കും ഇന്റർനെറ്റ് വേണം.",
                    pa="ਨਵੀਆਂ ਚੇਤਾਵਨੀਆਂ ਅਤੇ ਅੱਪਡੇਟ ਲਈ ਇੰਟਰਨੈੱਟ ਚਾਹੀਦਾ ਹੈ।",
                    or="ନୂଆ ଚେତାବନୀ ଓ ଅପଡେଟ୍ ପାଇଁ ଇଣ୍ଟରନେଟ୍ ଦରକାର।",
                )
                return (intro+warnings+"\n\n"+needNet) to day
            }
            val status=(b.official_status?:b.alerts_status).lowercase()
            val statusMsg=when(status) {
                "available" -> copy(lang,
                    en="Saved feed reported no active official warning here. New warnings need an internet connection. Refresh before going out.",
                    hi="सहेजी सेवा में यहाँ कोई सक्रिय आधिकारिक चेतावनी नहीं थी। नई चेतावनियों के लिए इंटरनेट चाहिए। बाहर जाने से पहले फिर जाँचें।",
                    bn="সংরক্ষিত ফিডে এখানে সক্রিয় সরকারি সতর্কতা ছিল না। নতুন সতর্কতার জন্য ইন্টারনেট দরকার। বাইরে যাওয়ার আগে আবার দেখুন।",
                    te="సేవ్ చేసిన ఫీడ్‌లో ఇక్కడ సక్రియ అధికారిక హెచ్చరిక లేదు. కొత్త హెచ్చరికలకు ఇంటర్నెట్ కావాలి. బయటకు వెళ్లే ముందు మళ్లీ చూడండి.",
                    mr="जतन फीडमध्ये येथे सक्रिय अधिकृत इशारा नव्हता. नवीन इशार्‍यांसाठी इंटरनेट लागते. बाहेर जाण्यापूर्वी पुन्हा तपासा.",
                    ta="சேமித்த ஊட்டத்தில் இங்கு செயலில் அதிகாரப்பூர்வ எச்சரிக்கை இல்லை. புதிய எச்சரிக்கைகளுக்கு இணையம் தேவை. வெளியே செல்வதற்கு முன் மீண்டும் பாருங்கள்.",
                    gu="સાચવેલા ફીડમાં અહીં સક્રિય અધિકૃત ચેતવણી નહોતી. નવી ચેતવણીઓ માટે ઇન્ટરનેટ જોઈએ. બહાર જતા પહેલાં ફરી તપાસો.",
                    kn="ಉಳಿಸಿದ ಫೀಡ್‌ನಲ್ಲಿ ಇಲ್ಲಿ ಸಕ್ರಿಯ ಅಧಿಕೃತ ಎಚ್ಚರಿಕೆ ಇರಲಿಲ್ಲ. ಹೊಸ ಎಚ್ಚರಿಕೆಗಳಿಗೆ ಇಂಟರ್ನೆಟ್ ಬೇಕು. ಹೊರಗೆ ಹೋಗುವ ಮೊದಲು ಮತ್ತೆ ನೋಡಿ.",
                    ml="സേവ് ചെയ്ത ഫീഡിൽ ഇവിടെ സജീവ ഔദ്യോഗിക മുന്നറിയിപ്പില്ലായിരുന്നു. പുതിയ മുന്നറിയിപ്പുകൾക്ക് ഇന്റർനെറ്റ് വേണം. പുറത്തിറങ്ങുന്നതിന് മുമ്പ് വീണ്ടും നോക്കുക.",
                    pa="ਸੰਭਾਲੀ ਫੀਡ ਵਿੱਚ ਇੱਥੇ ਕੋਈ ਸਰਗਰਮ ਅਧਿਕਾਰਤ ਚੇਤਾਵਨੀ ਨਹੀਂ ਸੀ। ਨਵੀਆਂ ਚੇਤਾਵਨੀਆਂ ਲਈ ਇੰਟਰਨੈੱਟ ਚਾਹੀਦਾ ਹੈ। ਬਾਹਰ ਜਾਣ ਤੋਂ ਪਹਿਲਾਂ ਫਿਰ ਜਾਂਚੋ।",
                    or="ସଞ୍ଚିତ ଫିଡ୍‌ରେ ଏଠାରେ ସକ୍ରିୟ ସରକାରୀ ଚେତାବନୀ ନଥିଲା। ନୂଆ ଚେତାବନୀ ପାଇଁ ଇଣ୍ଟରନେଟ୍ ଦରକାର। ବାହାରକୁ ଯିବା ପୂର୍ବରୁ ପୁନର୍ବାର ଦେଖନ୍ତୁ।",
                )
                else -> copy(lang,
                    en="New warnings need an internet connection. Official warning availability is unknown. Check IMD before going out.",
                    hi="नई चेतावनियों के लिए इंटरनेट चाहिए। आधिकारिक चेतावनी उपलब्धता पता नहीं है। बाहर जाने से पहले IMD की चेतावनी देखें।",
                    bn="নতুন সতর্কতার জন্য ইন্টারনেট দরকার। সরকারি সতর্কতা পাওয়া যায় কিনা জানা নেই। বাইরে যাওয়ার আগে IMD দেখুন।",
                    te="కొత్త హెచ్చరికలకు ఇంటర్నెట్ కావాలి. అధికారిక హెచ్చరిక లభ్యత తెలియదు. బయటకు వెళ్లే ముందు IMD చూడండి.",
                    mr="नवीन इशार्‍यांसाठी इंटरनेट लागते. अधिकृत इशारा उपलब्धता माहीत नाही. बाहेर जाण्यापूर्वी IMD पहा.",
                    ta="புதிய எச்சரிக்கைகளுக்கு இணையம் தேவை. அதிகாரப்பூர்வ எச்சரிக்கை கிடைக்குமா என தெரியவில்லை. வெளியே செல்வதற்கு முன் IMD பாருங்கள்.",
                    gu="નવી ચેતવણીઓ માટે ઇન્ટરનેટ જોઈએ. અધિકૃત ચેતવણી ઉપલબ્ધતા ખબર નથી. બહાર જતા પહેલાં IMD જુઓ.",
                    kn="ಹೊಸ ಎಚ್ಚರಿಕೆಗಳಿಗೆ ಇಂಟರ್ನೆಟ್ ಬೇಕು. ಅಧಿಕೃತ ಎಚ್ಚರಿಕೆ ಲಭ್ಯತೆ ತಿಳಿದಿಲ್ಲ. ಹೊರಗೆ ಹೋಗುವ ಮೊದಲು IMD ನೋಡಿ.",
                    ml="പുതിയ മുന്നറിയിപ്പുകൾക്ക് ഇന്റർനെറ്റ് വേണം. ഔദ്യോഗിക മുന്നറിയിപ്പ് ലഭ്യമോ എന്ന് അറിയില്ല. പുറത്തിറങ്ങുന്നതിന് മുമ്പ് IMD നോക്കുക.",
                    pa="ਨਵੀਆਂ ਚੇਤਾਵਨੀਆਂ ਲਈ ਇੰਟਰਨੈੱਟ ਚਾਹੀਦਾ ਹੈ। ਅਧਿਕਾਰਤ ਚੇਤਾਵਨੀ ਉਪਲਬਧਤਾ ਪਤਾ ਨਹੀਂ। ਬਾਹਰ ਜਾਣ ਤੋਂ ਪਹਿਲਾਂ IMD ਵੇਖੋ।",
                    or="ନୂଆ ଚେତାବନୀ ପାଇଁ ଇଣ୍ଟରନେଟ୍ ଦରକାର। ସରକାରୀ ଚେତାବନୀ ଉପଲବ୍ଧତା ଜଣାନାହିଁ। ବାହାରକୁ ଯିବା ପୂର୍ବରୁ IMD ଦେଖନ୍ତୁ।",
                )
            }
            return (intro+statusMsg) to day
        }
        if(listOf("climate","years","monsoon","जलवायु","decade","hotter").any{q.contains(it)}) {
            return (intro+copy(lang,
                en="Historical climate analysis needs an internet connection for ERA5 data. Reconnect to ask about long-term trends.",
                hi="ऐतिहासिक जलवायु विश्लेषण के लिए ERA5 डेटा हेतु इंटरनेट चाहिए। लंबे रुझान के लिए फिर जुड़ें।",
                bn="ঐতিহাসিক জলবায়ু বিশ্লেষণের জন্য ERA5 তথ্যে ইন্টারনেট দরকার। দীর্ঘ ধারার জন্য আবার যুক্ত হোন।",
                te="చారిత్రక వాతావరణ విశ్లేషణకు ERA5 డేటాకు ఇంటర్నెట్ కావాలి. దీర్ఘకాల ధోరణుల కోసం మళ్లీ కనెక్ట్ అవ్వండి.",
                mr="ऐतिहासिक हवामान विश्लेषणासाठी ERA5 डेटाकरिता इंटरनेट लागते. दीर्घकालाच्या कलसाठी पुन्हा जोडा.",
                ta="வரலாற்று காலநிலை பகுப்பாய்வுக்கு ERA5 தரவுக்கு இணையம் தேவை. நீண்ட போக்குகளுக்கு மீண்டும் இணையுங்கள்.",
                gu="ઐતિહાસિક આબોહવા વિશ્લેષણ માટે ERA5 ડેટા માટે ઇન્ટરનેટ જોઈએ. લાંબા વલણ માટે ફરી જોડાઓ.",
                kn="ಐತಿಹಾಸಿಕ ಹವಾಮಾನ ವಿಶ್ಲೇಷಣೆಗೆ ERA5 ಡೇಟಾಗೆ ಇಂಟರ್ನೆಟ್ ಬೇಕು. ದೀರ್ಘಕಾಲದ ಪ್ರವೃತ್ತಿಗೆ ಮತ್ತೆ ಸಂಪರ್ಕಿಸಿ.",
                ml="ചരിത്ര കാലാവസ്ഥാ വിശകലനത്തിന് ERA5 ഡാറ്റയ്ക്ക് ഇന്റർനെറ്റ് വേണം. ദീർഘകാല പ്രവണതയ്ക്ക് വീണ്ടും ബന്ധിപ്പിക്കുക.",
                pa="ਇਤਿਹਾਸਕ ਜਲਵਾਯੂ ਵਿਸ਼ਲੇਸ਼ਣ ਲਈ ERA5 ਡਾਟਾ ਲਈ ਇੰਟਰਨੈੱਟ ਚਾਹੀਦਾ ਹੈ। ਲੰਬੇ ਰੁਝਾਨ ਲਈ ਮੁੜ ਜੁੜੋ।",
                or="ଐତିହାସିକ ଜଳବାୟୁ ବିଶ୍ଳେଷଣ ପାଇଁ ERA5 ତଥ୍ୟ ପାଇଁ ଇଣ୍ଟରନେଟ୍ ଦରକାର। ଦୀର୍ଘକାଳୀନ ଧାରା ପାଇଁ ପୁଣି ଯୋଡନ୍ତୁ।",
            )) to day
        }
        if(!weatherWords.any{q.contains(it)}) return (intro+copy(lang,
            en="AI guidance is temporarily unavailable, but your downloaded weather is still available. Ask about rain, temperature, warnings, or best work time.",
            hi="AI मार्गदर्शन अभी उपलब्ध नहीं है, लेकिन आपका डाउनलोड किया मौसम उपलब्ध है। बारिश, तापमान, चेतावनी या काम के समय के बारे में पूछें।",
            bn="AI নির্দেশনা এখন নেই, কিন্তু আপনার ডাউনলোড করা আবহাওয়া আছে। বৃষ্টি, তাপমাত্রা, সতর্কতা বা কাজের সময় জিজ্ঞাসা করুন।",
            te="AI మార్గదర్శకం ప్రస్తుతం లేదు, కానీ మీ డౌన్‌లోడ్ వాతావరణం ఉంది. వర్షం, ఉష్ణోగ్రత, హెచ్చరికలు లేదా పని సమయం అడగండి.",
            mr="AI मार्गदर्शन सध्या उपलब्ध नाही, पण तुमचे डाउनलोड हवामान उपलब्ध आहे. पाऊस, तापमान, इशारे किंवा कामाची वेळ विचारा.",
            ta="AI வழிகாட்டல் தற்போது இல்லை, ஆனால் பதிவிறக்கிய வானிலை உள்ளது. மழை, வெப்பம், எச்சரிக்கை அல்லது வேலை நேரம் கேளுங்கள்.",
            gu="AI માર્ગદર્શન હાલ નથી, પણ તમારું ડાઉનલોડ હવામાન ઉપલબ્ધ છે. વરસાદ, તાપમાન, ચેતવણી કે કામના સમય વિશે પૂછો.",
            kn="AI ಮಾರ್ಗದರ್ಶನ ಈಗ ಲಭ್ಯವಿಲ್ಲ, ಆದರೆ ಡೌನ್‌ಲೋಡ್ ಹವಾಮಾನ ಲಭ್ಯ. ಮಳೆ, ತಾಪಮಾನ, ಎಚ್ಚರಿಕೆ ಅಥವಾ ಕೆಲಸದ ಸಮಯ ಕೇಳಿ.",
            ml="AI മാർഗനിർദേശം ഇപ്പോൾ ലഭ്യമല്ല, പക്ഷേ ഡൗൺലോഡ് കാലാവസ്ഥ ലഭ്യമാണ്. മഴ, താപനില, മുന്നറിയിപ്പ് അല്ലെങ്കിൽ ജോലി സമയം ചോദിക്കുക.",
            pa="AI ਮਾਰਗਦਰਸ਼ਨ ਹੁਣ ਉਪਲਬਧ ਨਹੀਂ, ਪਰ ਤੁਹਾਡਾ ਡਾਊਨਲੋਡ ਮੌਸਮ ਉਪਲਬਧ ਹੈ। ਮੀਂਹ, ਤਾਪਮਾਨ, ਚੇਤਾਵਨੀ ਜਾਂ ਕੰਮ ਦਾ ਸਮਾਂ ਪੁੱਛੋ।",
            or="AI ନିର୍ଦ୍ଦେଶ ବର୍ତ୍ତମାନ ନାହିଁ, କିନ୍ତୁ ଆପଣଙ୍କ ଡାଉନଲୋଡ୍ ପାଣିପାଗ ଅଛି। ବର୍ଷା, ତାପମାତ୍ରା, ଚେତାବନୀ କିମ୍ବା କାମ ସମୟ ପଚାରନ୍ତୁ।",
        )) to day
        val zone=ZoneId.of(b.location.timezone)
        val date=LocalDate.now(zone).plusDays(day.toLong())
        val rows=b.hourly.filter {
            val t=Instant.parse(it.time).atZone(zone)
            t.toLocalDate()==date && when {
                q.contains("morning") || q.contains("सुबह") || q.contains("காலை") -> t.hour in 6..11
                q.contains("afternoon") || q.contains("दोपहर") -> t.hour in 12..16
                q.contains("evening") || q.contains("शाम") || q.contains("மாலை") -> t.hour in 17..21
                else -> true
            }
        }
        if(rows.isEmpty()) return (intro+copy(lang,
            en="There is no saved weather for that time. Reconnect to refresh.",
            hi="उस समय का मौसम सहेजा नहीं गया है। नई जानकारी के लिए इंटरनेट से जुड़ें।",
            bn="সেই সময়ের সংরক্ষিত আবহাওয়া নেই। নতুন তথ্যের জন্য ইন্টারনেটে যুক্ত হোন।",
            te="ఆ సమయానికి సేవ్ చేసిన వాతావరణం లేదు. కొత్త సమాచారం కోసం ఇంటర్నెట్‌కు కనెక్ట్ అవ్వండి.",
            mr="त्या वेळेचे जतन हवामान नाही. नवीन माहितीसाठी इंटरनेटला जोडा.",
            ta="அந்த நேரத்திற்கு சேமித்த வானிலை இல்லை. புதிய தகவலுக்கு இணையத்துடன் இணையுங்கள்.",
            gu="તે સમયનું સાચવેલું હવામાન નથી. નવી માહિતી માટે ઇન્ટરનેટ જોડો.",
            kn="ಆ ಸಮಯಕ್ಕೆ ಉಳಿಸಿದ ಹವಾಮಾನ ಇಲ್ಲ. ಹೊಸ ಮಾಹಿತಿಗೆ ಇಂಟರ್ನೆಟ್ ಸಂಪರ್ಕಿಸಿ.",
            ml="ആ സമയത്തേക്ക് സേവ് ചെയ്ത കാലാവസ്ഥ ഇല്ല. പുതിയ വിവരത്തിന് ഇന്റർനെറ്റ് ബന്ധിപ്പിക്കുക.",
            pa="ਉਸ ਵੇਲੇ ਦਾ ਸੰਭਾਲਿਆ ਮੌਸਮ ਨਹੀਂ। ਨਵੀਂ ਜਾਣਕਾਰੀ ਲਈ ਇੰਟਰਨੈੱਟ ਜੋੜੋ।",
            or="ସେହି ସମୟର ସଞ୍ଚିତ ପାଣିପାଗ ନାହିଁ। ନୂଆ ସୂଚନା ପାଇଁ ଇଣ୍ଟରନେଟ୍ ଯୋଡନ୍ତୁ।",
        )) to day
        val temps=rows.mapNotNull{it.temperature}; val rain=rows.mapNotNull{it.rain_chance}
        val facts=buildList {
            add("${b.location.name} · $date")
            if(temps.isNotEmpty()) add(copy(lang,
                en="Temperature: ${temps.min()} to ${temps.max()}°C.",
                hi="तापमान: ${temps.min()} से ${temps.max()}°C।",
                bn="তাপমাত্রা: ${temps.min()} থেকে ${temps.max()}°C।",
                te="ఉష్ణోగ్రత: ${temps.min()} నుండి ${temps.max()}°C.",
                ta="வெப்பநிலை: ${temps.min()} முதல் ${temps.max()}°C.",
                mr="तापमान: ${temps.min()} ते ${temps.max()}°C.",
                gu="તાપમાન: ${temps.min()} થી ${temps.max()}°C.",
                kn="ತಾಪಮಾನ: ${temps.min()} ರಿಂದ ${temps.max()}°C.",
                ml="താപനില: ${temps.min()} മുതൽ ${temps.max()}°C.",
                pa="ਤਾਪਮਾਨ: ${temps.min()} ਤੋਂ ${temps.max()}°C।",
                or="ତାପମାତ୍ରା: ${temps.min()} ରୁ ${temps.max()}°C।",
            ))
            if(rain.isNotEmpty()) add(copy(lang,
                en="Highest hourly chance of rain: ${rain.max()}%.",
                hi="बारिश की सबसे अधिक संभावना: ${rain.max()}%.",
                bn="বৃষ্টির সর্বোচ্চ সম্ভাবনা: ${rain.max()}%.",
                te="అత్యధిక వర్ష అవకాశం: ${rain.max()}%.",
                ta="அதிகபட்ச மழை வாய்ப்பு: ${rain.max()}%.",
                mr="पावसाची सर्वाधिक शक्यता: ${rain.max()}%.",
                gu="વરસાદની સૌથી વધુ શક્યતા: ${rain.max()}%.",
                kn="ಅತ್ಯಧಿಕ ಮಳೆ ಸಾಧ್ಯತೆ: ${rain.max()}%.",
                ml="ഏറ്റവും ഉയർന്ന മഴ സാധ്യത: ${rain.max()}%.",
                pa="ਮੀਂਹ ਦੀ ਸਭ ਤੋਂ ਵੱਧ ਸੰਭਾਵਨਾ: ${rain.max()}%.",
                or="ସର୍ବାଧିକ ବର୍ଷା ସମ୍ଭାବନା: ${rain.max()}%.",
            ))
            add(copy(lang,
                en="Check official warnings before going out.",
                hi="बाहर जाने से पहले आधिकारिक चेतावनी देखें।",
                bn="বাইরে যাওয়ার আগে সরকারি সতর্কতা দেখুন।",
                te="బయటకు వెళ్లే ముందు అధికారిక హెచ్చరికలు చూడండి.",
                mr="बाहेर जाण्यापूर्वी अधिकृत इशारे पहा.",
                ta="வெளியே செல்லும் முன் அதிகாரப்பூர்வ எச்சரிக்கைகளை பாருங்கள்.",
                gu="બહાર જતા પહેલાં અધિકૃત ચેતવણીઓ જુઓ.",
                kn="ಹೊರಗೆ ಹೋಗುವ ಮೊದಲು ಅಧಿಕೃತ ಎಚ್ಚರಿಕೆಗಳನ್ನು ನೋಡಿ.",
                ml="പുറത്തിറങ്ങുന്നതിന് മുമ്പ് ഔദ്യോഗിക മുന്നറിയിപ്പുകൾ നോക്കുക.",
                pa="ਬਾਹਰ ਜਾਣ ਤੋਂ ਪਹਿਲਾਂ ਅਧਿਕਾਰਤ ਚੇਤਾਵਨੀਆਂ ਵੇਖੋ।",
                or="ବାହାରକୁ ଯିବା ପୂର୍ବରୁ ସରକାରୀ ଚେତାବନୀ ଦେଖନ୍ତୁ।",
            ))
        }
        return (intro+facts.joinToString("\n\n")) to day
    }

    private fun normalize(language:String)=when(language.lowercase()) {
        "hi","bn","te","mr","ta","gu","kn","ml","pa","or","en" -> language.lowercase()
        else -> "en"
    }

    private fun copy(lang:String,en:String,hi:String=en,bn:String=en,te:String=en,ta:String=en,mr:String=en,gu:String=en,kn:String=en,ml:String=en,pa:String=en,or:String=en)=when(lang) {
        "hi" -> hi; "bn" -> bn; "te" -> te; "ta" -> ta; "mr" -> mr; "gu" -> gu; "kn" -> kn; "ml" -> ml; "pa" -> pa; "or" -> or; else -> en
    }
}

fun speechLocaleTag(language:String)=when(language.lowercase()) {
    "en" -> "en-IN"
    "hi" -> "hi-IN"
    "bn" -> "bn-IN"
    "te" -> "te-IN"
    "mr" -> "mr-IN"
    "ta" -> "ta-IN"
    "gu" -> "gu-IN"
    "kn" -> "kn-IN"
    "ml" -> "ml-IN"
    "pa" -> "pa-IN"
    "or" -> "or-IN"
    else -> language
}

fun cachedAlertIsActive(alert:OfficialAlert,now:java.time.Instant=java.time.Instant.now()):Boolean {
    val effective=alert.effective?.let { runCatching { java.time.Instant.parse(it) }.getOrNull() }
    val expires=alert.expires?.let { runCatching { java.time.Instant.parse(it) }.getOrNull() }?:return false
    return (effective==null || !effective.isAfter(now)) && expires.isAfter(now)
}

enum class AlertLevel { YELLOW, ORANGE, RED }
fun alertLevel(severity:String):AlertLevel=when(severity.lowercase()) {
    "extreme","severe" -> AlertLevel.RED
    "moderate" -> AlertLevel.ORANGE
    else -> AlertLevel.YELLOW
}

fun titledSeverity(severity:String):String=
    severity.replaceFirstChar { ch -> if (ch.isLowerCase()) ch.titlecase(java.util.Locale.ROOT) else ch.toString() }

fun weatherScoreTalkBack(scoreLabel:String,value:Int?,agreement:String,unavailable:String):String {
    val number=value?.let { "$it / 100" } ?: unavailable
    return "$scoreLabel, $number, $agreement"
}

fun officialWarningTalkBack(warningLabel:String,severity:String,headline:String,instruction:String?=null):String=buildString {
    append(warningLabel)
    append(". ")
    append(titledSeverity(severity))
    if (headline.isNotBlank()) {
        append(". ")
        append(headline)
    }
    if (!instruction.isNullOrBlank()) {
        append(". ")
        append(instruction)
    }
}

fun hourlyTalkBack(time:String,temperature:String,rainLabel:String,rainChance:String):String=
    "$time, $temperature, $rainLabel $rainChance"

fun dailyForecastTalkBack(date:String,range:String,rainLabel:String,rainChance:String):String=
    "$date, $range, $rainLabel $rainChance"

fun purposeToProfile(purpose:String)=when(purpose.lowercase()) {
    "farm","farming" -> "farming"
    "harbour","fishing","harbor" -> "fishing"
    "work","construction","outdoor" -> "outdoor"
    else -> "general"
}
