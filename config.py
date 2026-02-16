"""
Configuration for Iqra AI.
"""

import os

# ASR model (Tarteel only)
DEFAULT_ASR_MODEL = "tarteel-ai/whisper-base-ar-quran"

# Tanzil XML (ceefour / qurandatabase) - Arabic only
TANZIL_BASE = "https://raw.githubusercontent.com/ceefour/qurandatabase/master"
QURAN_XML_URL = f"{TANZIL_BASE}/Arabic-(Original-Book)-1.xml"
ARABIC_XML_URL = QURAN_XML_URL  # alias

# Quran Enc API (JSON) - English + East African languages
# Endpoints: /translation/sura/{key}/{sura} and /translation/aya/{key}/{sura}/{aya}
QURANENC_BASE = "https://quranenc.com/api/v1/translation/sura"
QURANENC_TRANSLATIONS = {
    "en": "english_rwwad",
    "somali": "somali_yacob",
    "amharic": "amharic_sadiq",
    "swahili": "swahili_rwwad",
}

# Full translation list: Arabic (Tanzil XML) + English/Somali/Amharic/Swahili (Quran Enc API)
TRANSLATION_LANGS = ["ar", "en", "somali", "amharic", "swahili"]

# Project paths
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
ARABIC_XML_PATH = os.path.join(DATA_DIR, "Arabic-(Original-Book)-1.xml")
