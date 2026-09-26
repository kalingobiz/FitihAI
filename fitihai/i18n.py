"""Supported languages, the mandatory disclaimer, and short UI strings.

NOTE: the Amharic, Afaan Oromo and Tigrinya strings below are first drafts and
must be reviewed by native-speaking lawyers before public launch.
"""

from __future__ import annotations

LANGUAGES: dict[str, str] = {
    "am": "አማርኛ",
    "om": "Afaan Oromoo",
    "ti": "ትግርኛ",
    "en": "English",
}

LANGUAGE_NAMES_EN: dict[str, str] = {
    "am": "Amharic",
    "om": "Afaan Oromo",
    "ti": "Tigrinya",
    "en": "English",
}

DEFAULT_LANGUAGE = "am"

DISCLAIMER: dict[str, str] = {
    "en": (
        "This analysis is AI-generated and is intended for informational purposes only. "
        "It does not constitute legal advice. Before taking any action based on this "
        "information, please consult a licensed Ethiopian lawyer."
    ),
    "am": (
        "ይህ ትንታኔ በሰው ሰራሽ አስተውሎት (AI) የተዘጋጀ ሲሆን ለመረጃ ብቻ የታሰበ ነው። "
        "የሕግ ምክር አይደለም። በዚህ መረጃ ላይ ተመስርተው ማንኛውንም እርምጃ ከመውሰድዎ በፊት "
        "ፈቃድ ያለው የኢትዮጵያ ጠበቃ ያማክሩ።"
    ),
    "om": (
        "Xiinxalli kun AI'n kan qophaa'e yoo ta'u, odeeffannoof qofa kan yaadameedha. "
        "Gorsa seeraa miti. Odeeffannoo kana irratti hundaa'uun tarkaanfii kamiyyuu "
        "fudhachuu keessan dura, abukaatoo Itoophiyaa hayyama qabu mariisisaa."
    ),
    "ti": (
        "እዚ ትንተና ብሰብ ሰራሽ ኣእምሮ (AI) ዝተዳለወ ኮይኑ ንሓበሬታ ጥራይ ዝዓለመ እዩ። "
        "ሕጋዊ ምኽሪ ኣይኮነን። ነዚ ሓበሬታ መሰረት ጌርኩም ዝኾነ ስጉምቲ ቅድሚ ምውሳድኩም፡ "
        "ፍቓድ ዘለዎ ኢትዮጵያዊ ጠበቓ ኣማኽሩ።"
    ),
}

UI: dict[str, dict[str, str]] = {
    "welcome": {
        "en": "Welcome to Fitih AI. Ask a legal question, or send a photo/PDF of a legal document.",
        "am": "እንኳን ወደ ፍትህ AI በደህና መጡ። የሕግ ጥያቄ ይጠይቁ፣ ወይም የሕግ ሰነድ ፎቶ/PDF ይላኩ።",
        "om": "Baga gara Fitih AI dhuftan. Gaaffii seeraa gaafadhaa, yookaan suuraa/PDF sanada seeraa ergaa.",
        "ti": "እንቋዕ ናብ ፍትሕ AI ብደሓን መጻእኩም። ሕጋዊ ሕቶ ሕተቱ፣ ወይ ስእሊ/PDF ሕጋዊ ሰነድ ስደዱ።",
    },
    "choose_language": {
        "en": "Choose your language:",
        "am": "ቋንቋ ይምረጡ:",
        "om": "Afaan filadhaa:",
        "ti": "ቋንቋ ምረጹ:",
    },
    "working": {
        "en": "Reading and analysing… this can take up to a minute.",
        "am": "በማንበብና በመተንተን ላይ… እስከ አንድ ደቂቃ ሊወስድ ይችላል።",
        "om": "Dubbisaa fi xiinxalaa jira… hanga daqiiqaa tokkoo fudhachuu danda'a.",
        "ti": "ኣብ ምንባብን ምትንታንን… ክሳብ ሓንቲ ደቒቕ ክወስድ ይኽእል።",
    },
    "new_session": {
        "en": "Conversation cleared. Nothing from it is kept.",
        "am": "ውይይቱ ተሰርዟል። ምንም አልተቀመጠም።",
        "om": "Marii haqameera. Homtuu hin kuufamne.",
        "ti": "ዝርርብ ተሰሪዙ። ዝተዓቀበ የለን።",
    },
    "quota_exceeded": {
        "en": "You have used all free document analyses for this month.",
        "am": "የዚህ ወር ነፃ የሰነድ ትንታኔዎችን ሁሉ ተጠቅመዋል።",
        "om": "Xiinxala sanadaa bilisaa ji'a kanaa hunda fayyadamtaniittu.",
        "ti": "ናይዚ ወርሒ ነጻ ትንተና ሰነዳት ኩሉ ተጠቒምኩም።",
    },
    "voice_unsupported": {
        "en": "Voice messages are not supported yet. Please type your question.",
        "am": "የድምፅ መልዕክቶች ገና አይደገፉም። እባክዎ ጥያቄዎን ይፃፉ።",
        "om": "Ergaan sagalee ammaaf hin deeggaramu. Maaloo gaaffii keessan barreessaa.",
        "ti": "ናይ ድምጺ መልእኽቲ ገና ኣይድገፍን። በጃኹም ሕቶኹም ጽሓፉ።",
    },
    "error": {
        "en": "Sorry, something went wrong. Please try again.",
        "am": "ይቅርታ፣ ችግር ተፈጥሯል። እባክዎ እንደገና ይሞክሩ።",
        "om": "Dhiifama, rakkoon uumameera. Maaloo irra deebi'aa yaalaa.",
        "ti": "ይቕሬታ፣ ጸገም ኣጋጢሙ። በጃኹም እንደገና ፈትኑ።",
    },
    "sources": {"en": "Sources", "am": "ምንጮች", "om": "Madda", "ti": "ምንጪታት"},
    "deadlines": {"en": "Deadlines", "am": "የጊዜ ገደቦች", "om": "Yeroo murtaa'e", "ti": "ናይ ግዜ ገደባት"},
    "ask_lawyer": {
        "en": "Questions to ask a lawyer",
        "am": "ጠበቃን የሚጠይቋቸው ጥያቄዎች",
        "om": "Gaaffilee abukaatoo gaafattan",
        "ti": "ንጠበቓ እትሓትዎም ሕቶታት",
    },
}


def normalize_language(lang: str | None) -> str:
    lang = (lang or "").lower().strip()[:2]
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


def t(key: str, lang: str) -> str:
    table = UI[key]
    return table.get(lang) or table["en"]


def disclaimer(lang: str) -> str:
    return DISCLAIMER.get(lang) or DISCLAIMER["en"]
