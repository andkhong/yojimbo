"""Translation service wrapping Google Cloud Translation API.

Falls back to a pass-through when credentials are not configured,
allowing the app to run in development without a Google Cloud account.
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


async def _get_client():
    global _client
    if _client is not None:
        return _client
    if not settings.google_cloud_project_id:
        return None
    try:
        from google.cloud import translate_v3 as translate

        _client = translate.TranslationServiceAsyncClient()
        return _client
    except Exception:
        logger.warning("Google Cloud Translation client not available; translations disabled")
        return None


async def translate_text(
    text: str, target_language: str, source_language: str | None = None
) -> str:
    """Translate text to the target language.

    Returns the original text if translation is unavailable or unnecessary.
    """
    if not text or target_language == source_language:
        return text

    client = await _get_client()
    if client is None:
        return text

    try:
        parent = f"projects/{settings.google_cloud_project_id}/locations/global"
        request = {
            "parent": parent,
            "contents": [text],
            "target_language_code": target_language,
            "mime_type": "text/plain",
        }
        if source_language:
            request["source_language_code"] = source_language

        response = await client.translate_text(request=request)
        if response.translations:
            return response.translations[0].translated_text
    except Exception:
        logger.exception("Translation failed for text to %s", target_language)

    return text


async def detect_language(text: str) -> str:
    """Detect the language of the given text.

    Returns 'en' as default if detection is unavailable.
    """
    if not text:
        return "en"

    client = await _get_client()
    if client is None:
        return "en"

    try:
        parent = f"projects/{settings.google_cloud_project_id}/locations/global"
        response = await client.detect_language(
            parent=parent,
            content=text,
            mime_type="text/plain",
        )
        if response.languages:
            return response.languages[0].language_code
    except Exception:
        logger.exception("Language detection failed")

    return "en"
