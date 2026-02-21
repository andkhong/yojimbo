"""Twilio ConversationRelay TTS provider.

When using Twilio ConversationRelay, TTS is handled server-side by Twilio.
This provider is a no-op stub — text is sent back to Twilio via WebSocket
and Twilio converts it to speech using its own TTS engine.

Use ElevenLabsTTSProvider for higher-quality, lower-latency voice output.
"""

import logging

from app.services.tts.base import TTSProvider

logger = logging.getLogger(__name__)

# Twilio ConversationRelay TTS voices by language
# See: https://www.twilio.com/docs/voice/twiml/connect/conversation-relay
TWILIO_VOICES: dict[str, str] = {
    "en": "en-US-Neural2-F",
    "es": "es-US-Neural2-A",
    "zh": "cmn-CN-Wavenet-A",
    "vi": "vi-VN-Wavenet-A",
    "ko": "ko-KR-Wavenet-A",
    "tl": "fil-PH-Wavenet-A",
    "ar": "ar-XA-Wavenet-A",
    "fr": "fr-FR-Neural2-A",
    "de": "de-DE-Neural2-B",
    "ja": "ja-JP-Neural2-B",
    "pt": "pt-BR-Neural2-A",
    "ru": "ru-RU-Wavenet-A",
    "hi": "hi-IN-Neural2-A",
}


class TwilioTTSProvider(TTSProvider):
    """Twilio ConversationRelay pass-through TTS.

    No audio bytes are produced — Twilio handles TTS internally when
    the agent sends text back over the ConversationRelay WebSocket.
    """

    @property
    def name(self) -> str:
        return "twilio"

    @property
    def supports_streaming(self) -> bool:
        return False

    async def synthesize(
        self,
        text: str,
        language: str = "en",
        voice_id: str | None = None,
    ) -> bytes:
        """No-op: Twilio handles synthesis internally."""
        logger.debug("TwilioTTSProvider: synthesis handled by Twilio ConversationRelay")
        return b""

    def get_voice_for_language(self, language: str) -> str | None:
        return TWILIO_VOICES.get(language)
