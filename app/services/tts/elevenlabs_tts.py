"""ElevenLabs TTS provider — sub-100ms latency, 32+ languages.

Requires:
    pip install elevenlabs

Configuration (.env):
    ELEVENLABS_API_KEY=your_api_key
    ELEVENLABS_VOICE_ID=your_voice_id           # default: Rachel (en)
    ELEVENLABS_MODEL_ID=eleven_flash_v2_5       # lowest latency model

Architecture note:
    For use with Twilio <Stream> (not ConversationRelay):
    1. Twilio streams raw audio to our WebSocket
    2. We send to STT (e.g. Deepgram)
    3. Text goes to Gemini AI agent
    4. Response text comes here for synthesis
    5. We stream PCM audio bytes back to Twilio via <Stream>

    This replaces the ConversationRelay TTS with ElevenLabs' neural voices
    for dramatically better quality and <100ms first-byte latency.

ElevenLabs multilingual voices (recommended):
    - eleven_flash_v2_5: lowest latency, 32 languages (RECOMMENDED for live calls)
    - eleven_multilingual_v2: highest quality, 29 languages
    - eleven_turbo_v2_5: balance of quality and speed
"""

import logging
from typing import AsyncIterator

from app.services.tts.base import TTSProvider

logger = logging.getLogger(__name__)

# ElevenLabs voice IDs optimized per language
# Source: ElevenLabs voice library (voices with multilingual support)
ELEVENLABS_VOICES: dict[str, str] = {
    "en": "21m00Tcm4TlvDq8ikWAM",  # Rachel — warm, professional
    "es": "21m00Tcm4TlvDq8ikWAM",  # Rachel supports ES via multilingual model
    "zh": "21m00Tcm4TlvDq8ikWAM",  # Rachel supports ZH via multilingual model
    "vi": "21m00Tcm4TlvDq8ikWAM",
    "ko": "21m00Tcm4TlvDq8ikWAM",
    "tl": "21m00Tcm4TlvDq8ikWAM",
    "ar": "21m00Tcm4TlvDq8ikWAM",
    "fr": "21m00Tcm4TlvDq8ikWAM",
    "de": "21m00Tcm4TlvDq8ikWAM",
    "ja": "21m00Tcm4TlvDq8ikWAM",
}

# Model preference order (fastest first)
DEFAULT_MODEL = "eleven_flash_v2_5"


class ElevenLabsTTSProvider(TTSProvider):
    """ElevenLabs neural TTS with streaming support.

    Drop-in replacement for TwilioTTSProvider when ELEVENLABS_API_KEY is set.
    Provides sub-100ms first-byte latency via WebSocket streaming.
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model_id: str = DEFAULT_MODEL,
    ):
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._client = None

    def _get_client(self):
        """Lazy-init ElevenLabs client."""
        if self._client is not None:
            return self._client
        try:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(api_key=self._api_key)
            return self._client
        except ImportError as e:
            raise RuntimeError("ElevenLabs SDK not installed. Run: pip install elevenlabs") from e

    @property
    def name(self) -> str:
        return "elevenlabs"

    @property
    def supports_streaming(self) -> bool:
        return True

    async def synthesize(
        self,
        text: str,
        language: str = "en",
        voice_id: str | None = None,
    ) -> bytes:
        """Synthesize full audio — returns MP3 bytes.

        For live calls, prefer synthesize_stream() to start playing audio
        before the full response is generated.
        """
        import asyncio

        client = self._get_client()
        effective_voice = voice_id or self.get_voice_for_language(language) or self._voice_id

        loop = asyncio.get_event_loop()
        audio_bytes = await loop.run_in_executor(
            None,
            lambda: b"".join(
                client.text_to_speech.convert(
                    voice_id=effective_voice,
                    text=text,
                    model_id=self._model_id,
                    output_format="mp3_44100_128",
                )
            ),
        )
        logger.debug(
            "ElevenLabs synthesized %d chars → %d bytes audio",
            len(text),
            len(audio_bytes),
        )
        return audio_bytes

    async def synthesize_stream(
        self,
        text: str,
        language: str = "en",
        voice_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream audio chunks as they are generated (<100ms first byte).

        Yields MP3 chunks suitable for Twilio <Stream> or WebSocket delivery.
        """
        import asyncio

        client = self._get_client()
        effective_voice = voice_id or self.get_voice_for_language(language) or self._voice_id

        loop = asyncio.get_event_loop()

        def _stream():
            return client.text_to_speech.convert_as_stream(
                voice_id=effective_voice,
                text=text,
                model_id=self._model_id,
                output_format="mp3_44100_128",
            )

        stream = await loop.run_in_executor(None, _stream)
        for chunk in stream:
            if chunk:
                yield chunk

    def get_voice_for_language(self, language: str) -> str | None:
        return ELEVENLABS_VOICES.get(language, self._voice_id)
