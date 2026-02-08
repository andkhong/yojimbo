LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "zh": "Chinese",
    "vi": "Vietnamese",
    "ko": "Korean",
    "tl": "Tagalog",
    "ar": "Arabic",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
    "pt": "Portuguese",
    "ru": "Russian",
    "hi": "Hindi",
    "th": "Thai",
    "km": "Khmer",
}

# Twilio ConversationRelay language codes for TTS/STT
LANGUAGE_TTS_VOICES: dict[str, str] = {
    "en": "en-US-Neural2-F",
    "es": "es-US-Neural2-A",
    "zh": "cmn-CN-Neural2-A",
    "vi": "vi-VN-Neural2-A",
    "ko": "ko-KR-Neural2-A",
    "tl": "fil-PH-Neural2-A",
    "ar": "ar-XA-Neural2-A",
    "fr": "fr-FR-Neural2-A",
    "de": "de-DE-Neural2-A",
    "ja": "ja-JP-Neural2-B",
}

CALL_STATUSES = [
    "ringing",
    "in_progress",
    "completed",
    "failed",
    "no_answer",
    "busy",
    "cancelled",
]

APPOINTMENT_STATUSES = ["confirmed", "cancelled", "completed", "no_show"]
